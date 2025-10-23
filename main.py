import json
from pathlib import Path
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly_config import create_base_layout, apply_config_to_figure
from registry import WIDGETS, register_widget
import treasury_gov_pandas.datasets.deposits_withdrawals_operating_cash.load
import treasury_gov_pandas.datasets.mts.mts_table_4.load
import fed_net_liquidity
import _fed_balance_sheet
import datetime

# Get available dates from FRED data
df = _fed_balance_sheet.load_diff_dataframe()
if df is not None and not df.empty:
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').diff().reset_index()
    available_dates = sorted(
        df['date'].dt.strftime('%Y-%m-%d').unique(),
        reverse=True
    )
else:
    available_dates = []

# Create options list for the widget
date_options = [{"label": date, "value": date} for date in available_dates]

app = FastAPI()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT_PATH = Path(__file__).parent.resolve()


@app.get("/")
def read_root():
    return {"Info": "Full example for OpenBB Custom Backend"}


@app.get("/widgets.json")
async def get_widgets():
    return WIDGETS

@app.get("/templates.json")
async def get_templates():
    with open("templates.json", "r") as f:
        return json.load(f)

@app.get("/transactions")
@register_widget({
    "name": "Transactions",
    "description": (
        "Shows all transactions for a specific date with minimum amount filter"
    ),
    "category": "Treasury",
    "type": "chart",
    "endpoint": "transactions",
    "gridData": {"w": 40, "h": 15},
    "source": "U.S. Treasury",
    "data": {"chart": {"type": "bar"}},
    "params": [
        {
            "paramName": "metric",
            "value": "transaction_fytd_amt",
            "label": "Metric",
            "show": True,
            "description": "Select metric to display",
            "type": "text",
            "options": [
                {"label": "Today", "value": "transaction_today_amt"},
                {"label": "Month to Date", "value": "transaction_mtd_amt"},
                {"label": "Fiscal Year to Date", "value": "transaction_fytd_amt"}
            ],
        },
        {
            "paramName": "date",
            "value": "2025-01-02",
            "label": "Date",
            "show": True,
            "description": "Select date to view transactions",
            "type": "date"
        },
        {
            "paramName": "min_amount",
            "value": 100000,
            "label": "Minimum Amount",
            "show": True,
            "description": "Minimum transaction amount to display",
            "type": "number"
        }
    ],
})
def get_transactions(
    theme: str = "dark",
    metric: str = "transaction_fytd_amt",
    date: str = "2025-01-02",
    min_amount: int = 100000
):
    """Get daily transactions data and return as Plotly figure."""
    try:
        # Validate date format
        try:
            datetime.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return JSONResponse(
                content={
                    "error": "Invalid date format. Please use YYYY-MM-DD format."
                },
                status_code=400
            )

        # Load the dataframe
        try:
            df = treasury_gov_pandas.datasets.deposits_withdrawals_operating_cash.load.load()
        except ImportError:
            return JSONResponse(
                content={
                    "error": "treasury_gov_pandas package not found. Please install it."
                },
                status_code=500
            )
        except Exception as e:
            return JSONResponse(
                content={"error": f"Error loading data: {str(e)}"},
                status_code=500
            )

        # Convert numeric columns
        numeric_cols = [
            'transaction_today_amt',
            'transaction_mtd_amt',
            'transaction_fytd_amt'
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Filter out unwanted categories
        exclude_categories = [
            "null",
            "Sub-Total Withdrawals",
            "Sub-Total Deposits",
            "Transfers from Depositaries",
            "Transfers from Federal Reserve Account (Table V)",
            "Transfers to Depositaries",
            "Transfers to Federal Reserve Account (Table V)",
            "ShTransfersCtohFederalmReserve Account (Table V)"
        ]
        for cat in exclude_categories:
            df = df.query(f'transaction_catg != "{cat}"')

        # Filter for specific date
        df = df.query(f'record_date == "{date}"')
        
        # Check if data exists for the given date
        if df.empty:
            return JSONResponse(
                content={"error": f"No data available for date {date}"},
                status_code=404
            )

        # Convert withdrawals to negative values
        df.loc[df['transaction_type'] == 'Withdrawals', metric] = -df[metric]

        # Apply minimum amount filter
        df['absolute_value'] = df[metric].abs()
        df = df.query(f'absolute_value > {min_amount}')

        # Check if any data remains after filtering
        if df.empty:
            return JSONResponse(
                content={
                    "error": f"No transactions found above minimum amount {min_amount}"
                },
                status_code=404
            )

        # Sort by metric value (from negative to positive)
        df = df.sort_values(metric, ascending=True)

        # Create the figure
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df['transaction_catg'],
            y=df[metric],
            text=df[metric].apply(lambda x: f"${x:,.2f}"),
            textposition='auto',
            marker_color=df[metric].apply(
                lambda x: 'red' if x < 0 else 'green'
            )
        ))

        # Set the layout
        fig.update_layout(
            create_base_layout(
                x_title="Transaction Category",
                y_title="Transaction Amount",
                theme=theme
            ),
            xaxis_tickangle=-45,
            showlegend=False
        )

        # Apply theme configuration
        fig = apply_config_to_figure(fig, theme)

        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/fed-net-liquidity")
@register_widget({
    "name": "Fed Net Liquidity",
    "description": "Shows Federal Reserve Net Liquidity metrics including WALCL, RRP, TGA, REM and NL",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "fed-net-liquidity",
    "gridData": {"w": 40, "h": 15},
    "source": "Federal Reserve",
    "data": {"chart": {"type": "line"}},
    "params": [
        {
            "paramName": "start_date",
            "value": (datetime.datetime.now() - datetime.timedelta(days=3*365)).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        },
        {
            "paramName": "metric",
            "value": "NL",
            "label": "Metric",
            "show": True,
            "description": "Select metric to display",
            "type": "text",
            "options": [
                {"label": "Net Liquidity", "value": "NL"},
                {"label": "WALCL", "value": "WALCL"},
                {"label": "RRP", "value": "RRP"},
                {"label": "TGA", "value": "TGA"},
                {"label": "REM", "value": "REM"}
            ]
        }
    ],
})
def get_fed_net_liquidity(
    start_date: str = "2023-01-01",
    metric: str = "NL",
    theme: str = "dark"
):
    """Get Federal Reserve Net Liquidity data and return as Plotly figure."""
    try:
        # Load the dataframe
        df = fed_net_liquidity.load_dataframe()

        # Filter by date
        df = df[df['date'] > start_date]

        # Create subplots with 2 rows
        fig = make_subplots(
            rows=2, 
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3]
        )

        # Add main line chart
        fig.add_trace(
            go.Scatter(
                x=df['date'],
                y=df[metric],
                mode='lines',
                name=metric,
            ),
            row=1, col=1
        )

        # Add diff bar chart if available
        diff_col = f"{metric}_diff"
        if diff_col in df.columns:
            # Create separate traces for positive and negative values
            positive_mask = df[diff_col] >= 0
            negative_mask = df[diff_col] < 0
            
            # Add positive values trace
            fig.add_trace(
                go.Bar(
                    x=df.loc[positive_mask, 'date'],
                    y=df.loc[positive_mask, diff_col],
                    name=f"{metric} Increase",
                    marker_color='green'
                ),
                row=2, col=1
            )
            
            # Add negative values trace
            fig.add_trace(
                go.Bar(
                    x=df.loc[negative_mask, 'date'],
                    y=df.loc[negative_mask, diff_col],
                    name=f"{metric} Decrease",
                    marker_color='red'
                ),
                row=2, col=1
            )

        # Set the layout
        fig.update_layout(
            create_base_layout(
                x_title="Date",
                y_title="Amount (Billions)",
                theme=theme
            ),
            xaxis_tickangle=-45
        )

        # Apply theme configuration
        fig = apply_config_to_figure(fig, theme)

        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/fed-net-liquidity-all")
@register_widget({
    "name": "Fed Net Liquidity All",
    "description": "Shows all Federal Reserve Net Liquidity metrics including WALCL, RRP, TGA, REM and NL",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "fed-net-liquidity-all",
    "gridData": {"w": 40, "h": 15},
    "source": "Federal Reserve",
    "data": {"chart": {"type": "line"}},
    "params": [
        {
            "paramName": "start_date",
            "value": (datetime.datetime.now() - datetime.timedelta(days=3*365)).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        }
    ],
})
def get_fed_net_liquidity(
    start_date: str = "2023-01-01",
    theme: str = "dark"
):
    """Get Federal Reserve Net Liquidity data and return as Plotly figure."""
    try:
        # Load the dataframe
        df = fed_net_liquidity.load_dataframe()

        # Filter by date
        df = df[df['date'] > start_date]

        # Create figure
        fig = go.Figure()

        # Add all metrics as separate traces
        metrics = ["NL", "WALCL", "RRP", "TGA", "REM"]
        colors = ["#00ff00", "#00a7ff", "#00a7ff", "#ff69b4", "#ff0000"]
        for metric, color in zip(metrics, colors):
            fig.add_trace(
                go.Scatter(
                    x=df['date'],
                    y=df[metric],
                    mode='lines',
                    name=metric,
                    line=dict(color=color)
                )
            )

        # Set the layout
        fig.update_layout(
            create_base_layout(
                x_title="Date",
                y_title="Amount (Billions)",
                theme=theme
            ),
            xaxis_tickangle=-45
        )

        # Apply theme configuration
        fig = apply_config_to_figure(fig, theme)

        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/fed-net-liquidity-data")
@register_widget({
    "name": "Fed Net Liquidity Data",
    "description": "Shows Federal Reserve Net Liquidity metrics as a dataframe",
    "category": "Treasury",
    "type": "table",
    "endpoint": "fed-net-liquidity-data",
    "gridData": {"w": 40, "h": 15},
    "source": "Federal Reserve",
    "data": {
        "table" : {
            "showAll": True,
            "columnsDefs": [
                {
                    "field": "WALCL Change",
                    "headerName": "WALCL Change",
                    "cellDataType": "number",
                    "renderFn": "greenRed"
                },
                {
                    "field": "RRP Change",
                    "headerName": "RRP Change",
                    "cellDataType": "number",
                    "renderFn": "greenRed"
                },
                {
                    "field": "TGA Change",
                    "headerName": "TGA Change",
                    "cellDataType": "number",
                    "renderFn": "greenRed"
                },
                {
                    "field": "REM Change",
                    "headerName": "REM Change",
                    "cellDataType": "number",
                    "renderFn": "greenRed"
                },
                {
                    "field": "NL Change",
                    "headerName": "NL Change",
                    "cellDataType": "number",
                    "renderFn": "greenRed"
                }
            ]
        }
    },
    "params": [
        {
            "paramName": "start_date",
            "value": (datetime.datetime.now() - datetime.timedelta(days=3*365)).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        }
    ],
})
def get_fed_net_liquidity_data(
    start_date: str = "2023-01-01"
):
    """Get Federal Reserve Net Liquidity data and return as a dataframe."""
    try:
        # Load the dataframe
        df = fed_net_liquidity.load_dataframe()

        # Filter by date
        df = df[df['date'] > start_date]

        # Select and rename columns
        df = df[['date', 'WALCL', 'WALCL_diff', 'RRP', 'RRP_diff', 'TGA', 'TGA_diff', 'REM', 'REM_diff', 'NL', 'NL_diff']]
        df = df.rename(columns={
            'WALCL_diff': 'WALCL Change',
            'RRP_diff': 'RRP Change',
            'TGA_diff': 'TGA Change',
            'REM_diff': 'REM Change',
            'NL_diff': 'NL Change'
        })

        # Format numbers in billions
        def format_billions(x):
            return round(x / 1_000_000_000, 2)

        # Apply formatting to all numeric columns
        numeric_cols = ['WALCL', 'RRP', 'TGA', 'REM', 'NL', 'WALCL Change', 'RRP Change', 'TGA Change', 'REM Change', 'NL Change']
        for col in numeric_cols:
            df[col] = df[col].apply(format_billions)

        # Convert to dictionary for JSON response
        return df.to_dict(orient="records")
    
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/fed-balance-sheet")
@register_widget({
    "name": "Federal Reserve Balance Sheet",
    "description": (
        "Shows the Federal Reserve's balance sheet components over time"
    ),
    "category": "Treasury",
    "type": "chart",
    "endpoint": "fed-balance-sheet",
    "gridData": {"w": 40, "h": 15},
    "source": "Federal Reserve",
    "data": {"chart": {"type": "bar"}},
    "params": [
        {
            "paramName": "start_date",
            "value": (
                datetime.datetime.now() - datetime.timedelta(days=20*365)
            ).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        },
        {
            "paramName": "item",
            "value": "all",
            "label": "Item",
            "show": True,
            "description": "Select items to display",
            "type": "text",
            "options": [
                {"label": "All Items", "value": "all"},
                {"label": "Assets Only", "value": "assets"},
                {"label": "Liabilities Only", "value": "liabilities"}
            ],
            "style": {
                "popupWidth": 300
            }
        }
    ],
})
def get_fed_balance_sheet(
    start_date: str = "2005-01-01",
    item: str = "all",
    theme: str = "dark"
):
    """Get Federal Reserve balance sheet data and return as Plotly figure."""
    try:
        # Load the dataframe
        df = _fed_balance_sheet.load_dataframe()

        # Filter by date
        df = df[df['date'] > start_date]

        # Create the figure
        fig = go.Figure()

        # Determine which columns to display based on item selection
        columns_to_display = []
        if item == "assets":
            columns_to_display = list(_fed_balance_sheet.assets.keys())
        elif item == "liabilities":
            columns_to_display = list(_fed_balance_sheet.liabilities.keys())
        else:  # "all" or any other value
            columns_to_display = list(_fed_balance_sheet.all_items.keys())

        # Add traces for each component
        for column in df.columns[1:]:
            # Skip if column not in selected items
            if column not in columns_to_display:
                continue

            if column in _fed_balance_sheet.assets:
                name = f'A: {column} - {_fed_balance_sheet.all_items[column]}'
            elif column in _fed_balance_sheet.liabilities:
                name = f'L: {column} - {_fed_balance_sheet.all_items[column]}'
            else:
                name = f'{column} - {_fed_balance_sheet.all_items[column]}'

            fig.add_trace(
                go.Bar(
                    x=df['date'],
                    y=df[column],
                    name=name,
                    hovertemplate='<b>'+name+'</b><br>Date: %{x}<br>Value: %{y}<extra></extra>'
                )
            )

        # Set the layout
        fig.update_layout(
            create_base_layout(
                x_title="Date",
                y_title="Amount (Millions)",
                theme=theme
            ),
            barmode='relative',
            xaxis_tickangle=-45
        )

        # Apply theme configuration
        fig = apply_config_to_figure(fig, theme)

        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/fed-balance-sheet-weekly")
@register_widget({
    "name": "Federal Reserve Balance Sheet Weekly Changes",
    "description": (
        "Shows weekly changes in the Federal Reserve's balance sheet components"
    ),
    "category": "Treasury",
    "type": "chart",
    "endpoint": "fed-balance-sheet-weekly",
    "gridData": {"w": 40, "h": 15},
    "source": "Federal Reserve",
    "data": {"chart": {"type": "bar"}},
    "params": [
        {
            "paramName": "start_date_week",
            "value": "2025-03-26",
            "label": "Week Start Date",
            "show": True,
            "description": "Select week to view changes",
            "type": "text",
            "options": date_options
        }
    ],
})
def get_fed_balance_sheet_weekly(
    start_date_week: str = None,
    theme: str = "dark"
):
    """Get Federal Reserve balance sheet weekly changes and return as Plotly figure."""
    try:
        # Load the dataframe
        df = _fed_balance_sheet.load_diff_dataframe()

        # Convert date column to datetime if it's not already
        if not pd.api.types.is_datetime64_any_dtype(df['date']):
            df['date'] = pd.to_datetime(df['date'])

        # Get last year of data
        one_year_ago = datetime.datetime.now() - datetime.timedelta(days=365)
        df = df[df['date'] > one_year_ago]

        # Calculate weekly changes
        df = df.set_index('date').diff().reset_index()

        # Check if start_date_week is provided
        if start_date_week is None:
            return JSONResponse(
                content={"error": "start_date_week parameter is required"},
                status_code=400
            )

        # Convert start_date_week to datetime for comparison
        start_date_dt = datetime.datetime.strptime(start_date_week, "%Y-%m-%d")

        # Get data for selected week
        week_data = df[df['date'].dt.date == start_date_dt.date()]
        
        # Check if week_data is empty
        if week_data.empty:
            return JSONResponse(
                content={"error": f"No data found for date {start_date_week}"},
                status_code=404
            )
            
        week_data = week_data.iloc[0]

        # Create the figure
        fig = go.Figure()

        # Add traces for assets and liabilities
        for column in df.columns[1:]:
            if column in _fed_balance_sheet.assets:
                name = f'A: {column} - {_fed_balance_sheet.all_items[column]}'
                color = 'green'
            elif column in _fed_balance_sheet.liabilities:
                name = f'L: {column} - {_fed_balance_sheet.all_items[column]}'
                color = 'red'
            else:
                name = f'{column} - {_fed_balance_sheet.all_items[column]}'
                color = 'blue'

            fig.add_trace(
                go.Bar(
                    x=[name],
                    y=[week_data[column]],
                    name=name,
                    marker_color=color,
                    hovertemplate='<b>'+name+'</b><br>Change: %{y}<extra></extra>'
                )
            )

        # Set the layout
        fig.update_layout(
            create_base_layout(
                x_title="Balance Sheet Component",
                y_title="Weekly Change (Millions)",
                theme=theme
            ),
            barmode='group',
            xaxis_tickangle=-45
        )

        # Apply theme configuration
        fig = apply_config_to_figure(fig, theme)

        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/mts-income-taxes-monthly")
@register_widget({
    "name": "MTS Income Taxes - Monthly",
    "description": "Shows monthly individual income tax receipts for selected year and previous years",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "mts-income-taxes-monthly",
    "gridData": {"w": 40, "h": 15},
    "source": "U.S. Treasury",
    "data": {"chart": {"type": "bar"}},
    "params": [
        {
            "paramName": "year",
            "value": datetime.datetime.now().year-10,
            "label": "Year",
            "show": True,
            "description": "Select year to display",
            "type": "text",
            "options": [
                {"label": str(year), "value": year}
                for year in range(
                    datetime.datetime.now().year - 10,
                    datetime.datetime.now().year + 1
                )
            ]
        }
    ],
})
def get_mts_income_taxes_monthly(
    year: int = datetime.datetime.now().year-10,
    theme: str = "dark"
):
    """Get MTS Income Tax monthly data and return as Plotly figure."""
    try:
        df = treasury_gov_pandas.datasets.mts.mts_table_4.load.load()
        df['record_date'] = pd.to_datetime(df['record_date'])
        df['current_month_net_rcpt_amt'] = pd.to_numeric(
            df['current_month_net_rcpt_amt'], errors='coerce'
        )

        df = df.query('classification_desc == "Total -- Individual Income Taxes"')

        # Filter for selected year and previous years
        df = df[
            (df['record_calendar_year'].astype(int) >= int(year) - 1) &
            (df['record_calendar_year'].astype(int) <= int(year))
        ]

        fig = go.Figure()
        
        # Add a trace for each year
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        for year_val in sorted(df['record_calendar_year'].unique()):
            year_data = df[df['record_calendar_year'] == year_val]
            # Create a mapping from month number to month name
            year_data = year_data.copy()  # Create a copy to avoid SettingWithCopyWarning
            year_data['month_name'] = year_data['record_calendar_month'].map(
                lambda x: month_names[int(x)-1]
            )
            # Sort by original month number to maintain chronological order
            year_data = year_data.sort_values('record_calendar_month')
            
            fig.add_trace(
                go.Bar(
                    x=year_data['month_name'],
                    y=year_data['current_month_net_rcpt_amt'],
                    name=str(year_val),
                    hovertemplate='<b>%{fullData.name}</b><br>Month: %{x}<br>Amount: $%{y:,.2f}<extra></extra>'
                )
            )

        fig.update_layout(
            create_base_layout(
                x_title="Month",
                y_title="Amount",
                theme=theme
            ),
            barmode='group',
            xaxis_tickangle=-45
        )

        fig = apply_config_to_figure(fig, theme)
        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/mts-income-taxes-monthly-by-year")
@register_widget({
    "name": "MTS Income Taxes - Monthly by Year",
    "description": "Shows monthly individual income tax receipts by year",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "mts-income-taxes-monthly-by-year",
    "gridData": {"w": 40, "h": 15},
    "source": "U.S. Treasury",
    "data": {"chart": {"type": "line"}},
    "params": [
        {
            "paramName": "year",
            "value": datetime.datetime.now().year-10,
            "label": "Year",
            "show": True,
            "description": "Select year to display",
            "type": "text",
            "options": [
                {"label": str(year), "value": year}
                for year in range(
                    datetime.datetime.now().year - 10,
                    datetime.datetime.now().year + 1
                )
            ]
        }
    ],
})
def get_mts_income_taxes_monthly_by_year(
    year: int = datetime.datetime.now().year-10,
    theme: str = "dark"
):
    """Get MTS Income Tax monthly data by year and return as Plotly figure."""
    try:
        # Convert year to start date
        start_date = datetime.datetime(year, 1, 1)
        
        df = treasury_gov_pandas.datasets.mts.mts_table_4.load.load()
        df['record_date'] = pd.to_datetime(df['record_date'])
        df['current_month_net_rcpt_amt'] = pd.to_numeric(
            df['current_month_net_rcpt_amt'], errors='coerce'
        )

        df = df.query('classification_desc == "Total -- Individual Income Taxes"')
        df = df[df['record_date'] > start_date]

        pivot = df.pivot_table(
            values='current_month_net_rcpt_amt',
            index='record_calendar_month',
            columns='record_calendar_year'
        )
        melted = pivot.reset_index().melt(
            id_vars='record_calendar_month',
            value_name='current_month_net_rcpt_amt'
        )

        fig = go.Figure()
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        for year in melted['record_calendar_year'].unique():
            year_data = melted[melted['record_calendar_year'] == year]
            # Create a mapping from month number to month name
            year_data = year_data.copy()  # Create a copy to avoid SettingWithCopyWarning
            year_data['month_name'] = year_data['record_calendar_month'].map(
                lambda x: month_names[int(x)-1]
            )
            # Sort by original month number to maintain chronological order
            year_data = year_data.sort_values('record_calendar_month')
            
            fig.add_trace(
                go.Scatter(
                    x=year_data['month_name'],
                    y=year_data['current_month_net_rcpt_amt'],
                    name=str(year),
                    mode='lines'
                )
            )

        fig.update_layout(
            create_base_layout(
                x_title="Month",
                y_title="Amount",
                theme=theme
            ),
            xaxis_tickangle=-45
        )

        fig = apply_config_to_figure(fig, theme)
        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/mts-income-taxes-yoy-comparison")
@register_widget({
    "name": "MTS Income Taxes - YoY Comparison",
    "description": "Shows year-over-year comparison of individual income tax receipts",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "mts-income-taxes-yoy-comparison",
    "gridData": {"w": 40, "h": 15},
    "source": "U.S. Treasury",
    "data": {"chart": {"type": "bar"}},
    "params": [
        {
            "paramName": "start_date",
            "value": (datetime.datetime.now() - datetime.timedelta(days=10*365)).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        }
    ],
})
def get_mts_income_taxes_yoy_comparison(
    start_date: str = (datetime.datetime.now() - datetime.timedelta(days=10*365)).strftime("%Y-%m-%d"),
    theme: str = "dark"
):
    """Get MTS Income Tax YoY comparison data and return as Plotly figure."""
    try:
        df = treasury_gov_pandas.datasets.mts.mts_table_4.load.load()
        df['record_date'] = pd.to_datetime(df['record_date'])
        df['current_month_net_rcpt_amt'] = pd.to_numeric(
            df['current_month_net_rcpt_amt'], errors='coerce'
        )

        df = df.query('classification_desc == "Total -- Individual Income Taxes"')
        df = df[df['record_date'] > start_date]
        df = df.sort_values('record_date')

        df['prev_year'] = df['current_month_net_rcpt_amt'].shift(12)
        df['yoy_change'] = ((df['current_month_net_rcpt_amt'] - df['prev_year']) / df['prev_year']) * 100

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=df['record_date'],
                y=df['yoy_change'],
                name="YoY Change",
                hovertemplate='<b>YoY Change</b><br>Date: %{x}<br>Change: %{y:,.2f}%<extra></extra>'
            )
        )

        fig.update_layout(
            create_base_layout(
                x_title="Date",
                y_title="Percentage Change",
                theme=theme
            ),
            xaxis_tickangle=-45
        )

        fig = apply_config_to_figure(fig, theme)
        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/mts-income-taxes-current-vs-prior")
@register_widget({
    "name": "MTS Income Taxes - Current vs Prior Year",
    "description": "Shows current and prior year individual income tax receipts",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "mts-income-taxes-current-vs-prior",
    "gridData": {"w": 40, "h": 15},
    "source": "U.S. Treasury",
    "data": {"chart": {"type": "bar"}},
    "params": [
        {
            "paramName": "start_date",
            "value": (datetime.datetime.now() - datetime.timedelta(days=10*365)).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        }
    ],
})
def get_mts_income_taxes_current_vs_prior(
    start_date: str = (datetime.datetime.now() - datetime.timedelta(days=10*365)).strftime("%Y-%m-%d"),
    theme: str = "dark"
):
    """Get MTS Income Tax current vs prior year data and return as Plotly figure."""
    try:
        df = treasury_gov_pandas.datasets.mts.mts_table_4.load.load()
        df['record_date'] = pd.to_datetime(df['record_date'])
        df['current_month_net_rcpt_amt'] = pd.to_numeric(
            df['current_month_net_rcpt_amt'], errors='coerce'
        )

        df = df.query('classification_desc == "Total -- Individual Income Taxes"')
        df = df[df['record_date'] > start_date]
        df = df.sort_values('record_date')

        df['prev_year'] = df['current_month_net_rcpt_amt'].shift(12)

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=df['record_date'],
                y=df['current_month_net_rcpt_amt'],
                name="Current Year",
                hovertemplate='<b>Current Year</b><br>Date: %{x}<br>Amount: $%{y:,.2f}<extra></extra>'
            )
        )
        fig.add_trace(
            go.Bar(
                x=df['record_date'],
                y=df['prev_year'],
                name="Prior Year",
                hovertemplate='<b>Prior Year</b><br>Date: %{x}<br>Amount: $%{y:,.2f}<extra></extra>'
            )
        )

        fig.update_layout(
            create_base_layout(
                x_title="Date",
                y_title="Amount",
                theme=theme
            ),
            barmode='group',
            xaxis_tickangle=-45
        )

        fig = apply_config_to_figure(fig, theme)
        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/mts-income-taxes-fytd")
@register_widget({
    "name": "MTS Income Taxes - Fiscal Year-to-Date",
    "description": "Shows fiscal year-to-date individual income tax receipts",
    "category": "Treasury",
    "type": "chart",
    "endpoint": "mts-income-taxes-fytd",
    "gridData": {"w": 40, "h": 15},
    "source": "U.S. Treasury",
    "data": {"chart": {"type": "line"}},
    "params": [
        {
            "paramName": "start_date",
            "value": (datetime.datetime.now() - datetime.timedelta(days=10*365)).strftime("%Y-%m-%d"),
            "label": "Start Date",
            "show": True,
            "description": "Start date for the data",
            "type": "date"
        }
    ],
})
def get_mts_income_taxes_fytd(
    start_date: str = (datetime.datetime.now() - datetime.timedelta(days=10*365)).strftime("%Y-%m-%d"),
    theme: str = "dark"
):
    """Get MTS Income Tax fiscal year-to-date data and return as Plotly figure."""
    try:
        df = treasury_gov_pandas.datasets.mts.mts_table_4.load.load()
        df['record_date'] = pd.to_datetime(df['record_date'])
        df['current_fytd_net_rcpt_amt'] = pd.to_numeric(
            df['current_fytd_net_rcpt_amt'], errors='coerce'
        )
        df['prior_fytd_net_rcpt_amt'] = pd.to_numeric(
            df['prior_fytd_net_rcpt_amt'], errors='coerce'
        )

        df = df.query('classification_desc == "Total -- Individual Income Taxes"')
        df = df[df['record_date'] > start_date]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df['record_date'],
                y=df['current_fytd_net_rcpt_amt'],
                name="Current FYTD",
                mode='lines'
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df['record_date'],
                y=df['prior_fytd_net_rcpt_amt'],
                name="Prior FYTD",
                mode='lines'
            )
        )

        fig.update_layout(
            create_base_layout(
                x_title="Date",
                y_title="Amount",
                theme=theme
            ),
            xaxis_tickangle=-45
        )

        fig = apply_config_to_figure(fig, theme)
        return json.loads(fig.to_json())

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )
