import geopandas as gpd
import pandas as pd
import plotly.express as px
import json
import os
from dash import Dash, dcc, html, Input, Output, callback
from dash.dependencies import State
import webbrowser
from threading import Timer
import numpy as np

# === Configuration ===
# --- File Paths ---
shapefile_path = "./Deploy/ADA_shapefile/lada000b21a_e.shp"  # Canada ADA shapefile
simplified_shapefile_path = "./Deploy/ADA_shapefile/simplified_ada.shp"  # Simplified shapefile path
csv_path = "./Deploy/BD_dataset.csv"           # Immigration dataset

# --- Core Data Columns ---
shapefile_id_column = "ADAUID"
csv_id_column = "ADAUID"

print("=== Starting Canadian Immigration Map Visualization ===")

# === Load and Prepare Data (Only Done Once) ===
print(f"Reading shapefile: {simplified_shapefile_path}")
try:
    # Read shapefile with a more aggressive simplification to improve performance
    gdf = gpd.read_file(simplified_shapefile_path)
    gdf[shapefile_id_column] = gdf[shapefile_id_column].astype(str)
    print(f"Shapefile loaded successfully. Found {len(gdf)} regions.")
    print(f"Shapefile CRS: {gdf.crs}")
    
    # Convert CRS early to improve performance
    if gdf.crs is not None and gdf.crs != "EPSG:4326":
        print("Converting CRS to WGS84 (EPSG:4326)...")
        gdf = gdf.to_crs("EPSG:4326")
    
except Exception as e:
    print(f"Error loading shapefile: {e}")
    exit()

print(f"Reading CSV data: {csv_path}")
try:
    df_csv = pd.read_csv(csv_path)
    df_csv[csv_id_column] = df_csv[csv_id_column].astype(str)
    print(f"CSV data loaded successfully. Found {len(df_csv)} rows.")
except Exception as e:
    print(f"Error loading CSV file: {e}")
    exit()

# === Merge Shapefile Geometry with CSV Data ===
print(f"Merging geometry with data...")
gdf_merged = gdf.merge(df_csv, left_on=shapefile_id_column, right_on=csv_id_column, how="inner")
print(f"Rows after merge: {len(gdf_merged)}")
del gdf  # Free up memory by deleting the original GeoDataFrame

if len(gdf_merged) == 0:
    print("Error: Merge resulted in zero matching regions. Check if IDs match.")
    exit()

# === Prepare All Numeric Columns ===
print("Converting data columns to numeric...")
# Convert all T columns to numeric in one go
t_cols = [col for col in gdf_merged.columns if col.startswith('T') or col.startswith('Transit') or col.startswith('Walking')]
for col in t_cols:
    gdf_merged[col] = pd.to_numeric(gdf_merged[col], errors='coerce')

# === Create GeoJSON with Reduced Complexity ===
print("Preparing GeoJSON for Plotly...")
# Create a simplified copy for GeoJSON generation to improve performance
gdf_for_json = gdf_merged.copy()
# Further simplify for JSON creation if needed
gdf_for_json.geometry = gdf_for_json.geometry.simplify(0.002)  # Even more aggressive for the JSON
# Set the index to the shapefile ID column for GeoJSON generation
gdf_for_json = gdf_for_json.set_index(shapefile_id_column)
geojson_data = json.loads(gdf_for_json.to_json())
print(f"GeoJSON created with {len(geojson_data.get('features', []))} features.")


# Prepare the main dataframe without geometry to reduce memory usage
df_data = gdf_merged[[shapefile_id_column, 'PRNAME', 'CSDNAME', 'Average Score', 'Average Quintile', 'Population Weighted Score', 'ESAI-Norm', 'IDI_ADA', 'RII_ADA'] + t_cols].copy()
del gdf_merged  # Free up memory by deleting the merged GeoDataFrame


# === Define Immigration Data Columns ===
# Create dictionary of time periods
title_column_selector = {
    'Immigrant number': 'immigrant',
    'Score': 'Average Score',
    'Quintile': 'Average Quintile',
    'Weighted Score': 'Population Weighted Score'
}

time_periods = {
    'All Immigrants': 'T1529',
    'Before 1980': 'T1530',
    'From 1980 to 1990': 'T1531',
    'From 1991 to 2000': 'T1532',
    'From 2001 to 2010': 'T1533',
    'From 2011 to 2021': 'T1534',
    'From 2011 to 2015': 'T1535',
    'From 2016 to 2021': 'T1536'
}

# Create dictionary of origin regions
origin_regions = {
    'Total Immigrants': 'T1529',
    'Americas': 'T1545',
    'Europe': 'T1557',
    'Africa': 'T1574',
    'Asia': 'T1585', 
    'Oceania & Others': 'T1603'
}

# Create dictionary of specific origins (countries)
origin_countries = {
    # Americas
    'Brazil': 'T1546',
    'Colombia': 'T1547',
    'Haiti': 'T1550',
    'Jamaica': 'T1551',
    'Mexico': 'T1552',
    'USA': 'T1555',
    
    # Europe
    'France': 'T1560',
    'Germany': 'T1561',
    'Italy': 'T1564',
    'Poland': 'T1566',
    'Russia': 'T1569',
    'Ukraine': 'T1571',
    'UK': 'T1572',
    
    # Africa
    'Egypt': 'T1577',
    'Ethiopia': 'T1579',
    'Morocco': 'T1580',
    'Nigeria': 'T1581',
    'Somalia': 'T1582',
    
    # Asia
    'Afghanistan': 'T1586',
    'China': 'T1592',
    'India': 'T1599',
    'Iran': 'T1587',
    'Lebanon': 'T1589',
    'Pakistan': 'T1600',
    'Philippines': 'T1596',
    'Syria': 'T1590'
}

accessibility_modes = {
    'Public Transit': 'Transit_Accessibility',
    'Walking': "Walking_Accessibility"
}

# ESAI-Norm,IDI_ADA,RII_ADA

other_indicators = {
    'CIMD Score': 'Average Score',
    'Essential Services Accessibility Index (ESAI)': 'ESAI-Norm',
    'Immigration Density Index': 'IDI_ADA',
    'Recent Immigration Intensity': 'RII_ADA',
}

# === Create Dash App ===
print("\nSetting up Dash application...")
app = Dash(__name__)
server = app.server

# Custom CSS for better styling
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Canadian Immigration Map</title>
        {%favicon%}
        {%css%}
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Inter', sans-serif;
                margin: 0;
                padding: 15px;
                background-color: #121212;
                color: #ffffff;
            }
            .dash-dropdown, .Select-control, .Select-menu-outer {
                background-color: #2c2c2c !important;
                color: #ffffff !important;
            }
            .dash-dropdown .Select-placeholder,
            .dash-dropdown .Select-value-label {
                color: #ffffff !important;
            }
            .Select-menu-outer {
                background-color: #333333 !important;
            }
            .dash-loading, .dash-graph {
                background-color: #121212;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Define app layout
app.layout = html.Div([
    # Header with images and title
    html.Div([
        # Statistics Canada logo
        html.Img(src='assets/Images/stats_canada_logo.jpg', style={
            'height': '80px', 'marginRight': '20px'
        }),

        # Title in the center
        html.H1("Canada Immigration Map", style={
            'textAlign': 'center',
            'color': '#00BFFF',  # DeepSkyBlue
            'fontFamily': 'Segoe UI, sans-serif',
            'margin': '0 auto',
            'flexGrow': '1'
        }),

        # Bridging Divides logo
        html.Img(src='assets/Images/bd_data_challenge_logo.jpg', style={
            'height': '80px', 'marginLeft': '20px'
        })
    ], style={
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'space-between',
        'marginBottom': '20px',
        'padding': '10px 20px',
        'backgroundColor': '#1e1e1e',  # Optional dark background for header
        'borderRadius': '8px'
    }),
# Row 1: Period, Region, Country
    html.Div([
        html.Div([
            html.Label("Select Immigration Period:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='period-dropdown',
                options=[{'label': period, 'value': col} for period, col in time_periods.items()],
                value='T1529',
                clearable=False
            ),
        ], style={'width': '32%', 'display': 'inline-block', 'marginRight': '2%'}),

        html.Div([
            html.Label("Select Origin Region:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='region-dropdown',
                options=[{'label': region, 'value': col} for region, col in origin_regions.items()],
                value='T1529',
                clearable=False
            ),
        ], style={'width': '32%', 'display': 'inline-block', 'marginRight': '2%'}),

        html.Div([
            html.Label("Select Origin Country:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='country-dropdown',
                options=[{'label': country, 'value': col} for country, col in origin_countries.items()],
                value=None,
                clearable=True,
                placeholder="Select a country (optional)"
            ),
        ], style={'width': '32%', 'display': 'inline-block'})
    ], style={'marginBottom': '15px'}),

    # Row 2: Quantile, Accessibility, Data Type
    html.Div([
        html.Div([
            html.Label("Filter by Quantile:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='quantile-dropdown',
                options=[
                    {'label': 'Top 1%', 'value': 0.99},
                    {'label': 'Top 5%', 'value': 0.95},
                    {'label': 'Top 10%', 'value': 0.90},
                    {'label': 'Top 25%', 'value': 0.75},
                    {'label': 'All', 'value': 0.0}
                ],
                value=0.0,
                clearable=False
            ),
        ], style={'width': '32%', 'display': 'inline-block', 'marginRight': '2%'}),

        html.Div([
            html.Label("Select Accessibility Modes:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='accessibility-dropdown',
                options=[{'label': mode, 'value': col} for mode, col in accessibility_modes.items()],
                value=None,
                clearable=True,
                placeholder="Select a Mode (optional)"
            ),
        ], style={'width': '32%', 'display': 'inline-block', 'marginRight': '2%'}),

        html.Div([
            html.Label("Select Data Type:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='data-type-dropdown',
                options=[{'label': k, 'value': k} for k in title_column_selector],
                value='Immigrant number',
                clearable=False
            ),
        ], style={'width': '32%', 'display': 'inline-block'})
    ], style={'marginBottom': '20px'}),

    html.Div([
        html.Div([
            html.Label("Other Indicators:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='others-dropdown',
                options=[
                    {'label': ind, 'value': val} for ind, val in other_indicators.items()
                ],
                value=None,
                clearable=True
            ),
        ], style={'width': '32%', 'display': 'inline-block', 'marginRight': '2%'}),
    ], style={'marginBottom': '20px'}),
    
    # Main map and statistics container
    html.Div([
        # Map container - takes 75% of width
        html.Div([
            dcc.Loading(  # Specific loading indicator for the map
                id="loading-map",
                type="circle",
                children=[
                    dcc.Graph(id='immigration-map', style={'height': '75vh'})
                ]
            )
        ], style={'width': '75%', 'display': 'inline-block', 'verticalAlign': 'top'}),
        
        # Statistics panel - takes 25% of width
        html.Div([
            html.H3("Immigration Statistics", style={'textAlign': 'center', 'marginBottom': '15px'}),
            dcc.Loading(  # Specific loading indicator for the stats panel
                id="loading-stats",
                type="circle",
                children=[
                    html.Div(id='stats-panel', style={'padding': '10px'})
                ]
            )
        ], style={'width': '24%', 'display': 'inline-block', 'verticalAlign': 'top', 
                'marginLeft': '1%', 'backgroundColor': '#1e1e1e', 'color': 'white', 'borderRadius': '5px', 
                'height': '75vh', 'overflowY': 'auto'})
    ]),
    
    # Footer with data source information
    html.Div([
        html.P("Data Source: Statistics Canada 2021 Census - Bridging Divides Migration Data Challenge", 
            style={'textAlign': 'center', 'fontStyle': 'italic', 'marginTop': '20px'})
    ]),
    
    # Add a store component to cache data and prevent re-renders
    dcc.Store(id='cached-data', storage_type='memory')
])

# Define callback for updating map and statistics based on dropdown selections
@app.callback(
    [Output('immigration-map', 'figure'),
     Output('cached-data', 'data')],
    [Input('period-dropdown', 'value'),
     Input('region-dropdown', 'value'),
     Input('country-dropdown', 'value'),
     Input('accessibility-dropdown', 'value'),
     Input('quantile-dropdown', 'value'),
     Input('data-type-dropdown', 'value'),
     Input('others-dropdown', 'value')],
    # Prevent callback from being triggered by hover events
    prevent_initial_call=False
)
def update_map_and_stats(selected_period, selected_region, selected_country, selected_accessibility, selected_quantile, selected_data_type, selected_other_indicators):
    import time
    start_time = time.time()

    if selected_data_type != 'Immigrant number':
        data_column = title_column_selector[selected_data_type]
        map_title = f"{selected_data_type} by ADA"
    else:
        if selected_country:
            data_column = selected_country
        elif selected_other_indicators:
            data_column = selected_other_indicators
        elif selected_region != 'T1529':
            data_column = selected_region
        elif selected_accessibility:
            data_column = selected_accessibility
        else:
            data_column = selected_period
        map_title = f"Immigration by {data_column}"

    full_data = df_data[df_data[data_column].notna()].copy()
    threshold = full_data[data_column].quantile(selected_quantile)
    df_plot = full_data[full_data[data_column] >= threshold]

    if len(df_plot) == 0:
        return px.choropleth(title="No Data Available"), None

    max_value = df_plot[data_column].quantile(0.99)
    if max_value <= 0:
        max_value = df_plot[data_column].max()
    
    # Prepare additional data for hover information
    # Calculate percentage of total for each region
    total_immigrants = df_plot[data_column].sum()
    if total_immigrants > 0:
        df_plot['percent_of_total'] = (df_plot[data_column] / total_immigrants).round(4)*100  # Store as proportion
    else:
        df_plot['percent_of_total'] = 0
        
    # Create the choropleth map
    try:
        # Use a simplified mapbox approach for faster rendering
        fig = px.choropleth(
            df_plot,
            geojson=geojson_data,
            locations=shapefile_id_column,
            featureidkey="id",
            color=data_column,
            color_continuous_scale="Viridis",
            range_color=(0, max_value),
            custom_data=['PRNAME', 'CSDNAME', 'ADAUID', 'T1529', 'percent_of_total', 'Average Quintile', 'Average Score']
        )
        
        # Customize hover template
        hovertemplate = """
        <b>%{customdata[1]}, %{customdata[0]}</b><br>
        <b>ADAUID:</b> %{customdata[2]}<br>
        <b>Immigrants:</b> %{customdata[3]:,.0f}<br> 
        <b>Percentage of immigrants:</b> %{customdata[4]:.2%}<br> 
        <b>CIMD Quintile:</b> %{customdata[5]:.1f}<br>
        <b>CIMD Score:</b> %{customdata[6]:.1f}<br>
        <extra></extra>
        """
        
        # Apply the hover template
        fig.update_traces(hovertemplate=hovertemplate, marker_line_width=0, marker_opacity=1)
        
        # Add title
        fig.update_layout(title=map_title)
        
        # Simplified map settings for better performance
        fig.update_geos(
            fitbounds="locations",
            visible=True,
            showcoastlines=True,
            coastlinecolor="gray",
            showland=True,
            landcolor="black",         # Dark land
            showlakes=True,
            lakecolor="black",         # Match background
            showrivers=False,
            bgcolor="black"            # Entire map background
        )

        
        fig.update_layout(
            paper_bgcolor="black",     # Background outside the map
            plot_bgcolor="black",      # Background inside the plot area
            font=dict(color="white"),
            margin={"r": 0, "t": 40, "l": 0, "b": 0},
            coloraxis_colorbar=dict(
                title=dict(text=data_column, font=dict(color="white")),
                lenmode="fraction",
                len=0.75,
                thickness=20,
                xanchor="right",
                x=1.02,
                tickfont=dict(color="white")
            )
        )
    except Exception as e:
        print(f"Error creating map: {e}")
        return px.choropleth(title=f"Error: {str(e)}"), None

    return fig, df_plot.to_dict('records')

# Change callback to trigger on clickData for the stats-panel
@app.callback(
    Output('stats-panel', 'children'),
    [Input('immigration-map', 'clickData')], # Changed from hoverData to clickData
    [State('cached-data', 'data')]
)
def update_stats_on_click(click_data, cached_data_list): # Renamed function and first argument
    import time
    start_time = time.time()
    
    # If no click data is available, return message to click
    if not click_data or not cached_data_list:
        return html.Div("Click on a region to see details.") # Updated message
    
    # Get the clicked region data
    point = click_data['points'][0] # Using click_data
    if 'customdata' not in point or len(point['customdata']) < 7: 
        return html.Div("Click on a region to see details (customdata issue).")
    
    # Extract data from the click point
    province = point['customdata'][0] 
    city = point['customdata'][1]
    zone = point['customdata'][2]

    text_info_children = [
        html.H4(f"Selected Region: {city}, {province}, {zone}", 
                style={'borderBottom': '1px solid #4CAF50', 'paddingBottom': '8px', 'color': '#4CAF50'}),
        html.P([html.Strong("Total Immigrants (Region): "), f"{point['customdata'][3]:,.0f}"]),
        html.P([html.Strong("% of Immigrants: "), f"{(point['customdata'][4]*100):.2f}%"]), # Ensures multiplication by 100 and '%' sign
        html.P([html.Strong("CIMD Quintile: "), f"{point['customdata'][5]}"]),
        html.P([html.Strong("CIMD Score: "), f"{point['customdata'][6]:.2f}"]),
    ]

    # Pie chart logic
    region_id = point['location']
    hovered_region_data = None # Variable name can remain, context is now 'clicked'
    for region_data_dict in cached_data_list:
        if region_data_dict[shapefile_id_column] == region_id:
            hovered_region_data = region_data_dict
            break
    
    pie_chart_children = []
    if hovered_region_data:
        origin_pie_data = {}
        # Using origin_countries to get column names and labels for specific countries
        for label, col_name in origin_countries.items(): 
            origin_pie_data[label] = hovered_region_data.get(col_name, 0)
        
        # Calculate total for percentage calculation (sum of all specified origin countries)
        total_origin_sum = sum(value for value in origin_pie_data.values() if pd.notna(value) and value > 0)

        pie_labels = []
        pie_values = []
        others_sum = 0

        if total_origin_sum > 0: # Proceed only if there's any origin data
            for label, value in origin_pie_data.items():
                if pd.notna(value) and value > 0:
                    percentage = (value / total_origin_sum) * 100
                    if percentage > 2:
                        pie_labels.append(label)
                        pie_values.append(value)
                    else:
                        others_sum += value
            
            if others_sum > 0:
                pie_labels.append("Others (<2%)")
                pie_values.append(others_sum)

        if sum(pie_values) > 0: # Check if there's anything to plot after filtering
            pie_fig = px.pie(
                names=pie_labels, 
                values=pie_values, 
                title="Country of Origin Distribution", 
                hole=0.3,
                template="plotly_dark"
            )
            pie_fig.update_layout(
                margin=dict(t=40, b=0, l=0, r=0),
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)",  
                font=dict(color="white"),
                showlegend=False # Add this line to hide the legend
            )
            pie_fig.update_traces(textinfo='percent+label', textfont_size=10)
            pie_chart_children.append(dcc.Graph(figure=pie_fig, config={'displayModeBar': False}, style={'marginTop': '10px', 'padding': '20px'}))
        else:
            pie_chart_children.append(html.P("No detailed country of origin data available for this region.", style={'marginTop': '10px'})) 
    else:
        pie_chart_children.append(html.P("Region data not found in cache for pie chart.", style={'marginTop': '10px'}))

    # Time trend bar chart logic
    time_trend_chart_children = []
    if hovered_region_data: # Variable name can remain, context is now 'clicked'
        # Define the order and labels for the time trend chart
        # Combine the last two periods using T1534
        trend_periods_ordered = {
            'Before 1980': 'T1530',
            '1980-1990': 'T1531', 
            '1991-2000': 'T1532',
            '2001-2010': 'T1533',
            '2011-2021': 'T1534'  # Combined period using the existing T1534 column
        }
        
        trend_labels = []
        trend_values = []
        
        for label, col_name in trend_periods_ordered.items():
            value = hovered_region_data.get(col_name, 0)
            if pd.notna(value): 
                trend_labels.append(label)
                trend_values.append(value)
            else: 
                trend_labels.append(label)
                trend_values.append(0)

        if any(v > 0 for v in trend_values): 
            bar_fig = px.bar(
                x=trend_labels, 
                y=trend_values, 
                labels={'x': 'Period', 'y': 'Number of Immigrants'},
                title="Immigrant Trend Over Time"
            )
            bar_fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                xaxis_title="", 
                yaxis_title="Immigrants",
                margin=dict(t=40, b=0, l=0, r=0)
            )
            bar_fig.update_traces(marker_color='#00BFFF') 
            time_trend_chart_children.append(dcc.Graph(figure=bar_fig, config={'displayModeBar': False}, style={'marginTop': '20px'}))
        else:
            time_trend_chart_children.append(html.P("No time trend data available for this region.", style={'marginTop': '10px'}))
    else:
        time_trend_chart_children.append(html.P("Region data not found in cache for trend chart.", style={'marginTop': '10px'}))

    return html.Div(text_info_children + pie_chart_children + time_trend_chart_children)

# Function to automatically open the browser
def open_browser():
    try:
        webbrowser.open_new("http://127.0.0.1:8050/")
    except Exception as e:
        print(f"Could not open browser automatically: {e}")

if __name__ == '__main__':
    # print("Starting Dash server... Opening http://127.0.0.1:8050/ in your browser.")
    # Open the browser tab automatically after a short delay
    # Timer(1, open_browser).start()
    # Run the server
    app.run(debug=True, host='0.0.0.0')
