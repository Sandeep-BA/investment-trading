import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
import os # Import os module to check for file existence locally

# Define file names
pe_pb_div_file_name = "NIFTY_NEXT_50_Historical_PE_PB_DIV_Data_01062001to20062025.csv"
pr_file_name = "NIFTY_NEXT_50_Historical_PR_01062001to20062025.csv"

try:
    # Check if content_fetcher is available (i.e., running in the Canvas environment)
    if 'content_fetcher' in globals():
        print("Running in Canvas environment, using content_fetcher...")
        # Define file IDs based on the user's uploaded files for Canvas
        pe_pb_div_file_id = f"uploaded:{pe_pb_div_file_name}"
        pr_file_id = f"uploaded:{pr_file_name}"

        # Use content_fetcher to read the CSV files
        pe_pb_div_csv_content = content_fetcher.fetch(
            query="NIFTY_NEXT_50_Historical_PE_PB_DIV_Data",
            source_references=[{"id": pe_pb_div_file_id}]
        )
        pr_csv_content = content_fetcher.fetch(
            query="NIFTY_NEXT_50_Historical_PR_01062001to20062025",
            source_references=[{"id": pr_file_id}]
        )

        # Read the CSV content into pandas DataFrames from string
        pe_pb_div_df = pd.read_csv(io.StringIO(pe_pb_div_csv_content))
        pr_df = pd.read_csv(io.StringIO(pr_csv_content))
    else:
        print("Running locally, reading CSV files directly...")
        # For local execution, assume files are in the same directory
        # Add checks for local file existence before trying to read
        if not os.path.exists(pe_pb_div_file_name):
            raise FileNotFoundError(f"Local file not found: {pe_pb_div_file_name}. Please ensure it's in the same directory as the script.")
        if not os.path.exists(pr_file_name):
            raise FileNotFoundError(f"Local file not found: {pr_file_name}. Please ensure it's in the same directory as the script.")

        pe_pb_div_df = pd.read_csv(pe_pb_div_file_name)
        pr_df = pd.read_csv(pr_file_name)


    # --- Data Preprocessing ---

    # Convert 'Date' columns to datetime objects with the correct format
    # The format '20 Jun 2025' corresponds to '%d %b %Y'
    pe_pb_div_df['Date'] = pd.to_datetime(pe_pb_div_df['Date'], format='%d %b %Y')
    pr_df['Date'] = pd.to_datetime(pr_df['Date'], format='%d %b %Y')

    # Sort data by date to ensure proper plotting and merging
    pe_pb_div_df = pe_pb_div_df.sort_values(by='Date')
    pr_df = pr_df.sort_values(by='Date')

    # Merge the two dataframes on 'Date'
    # Use inner join to only keep dates present in both files, ensuring we have both PE and Close price
    merged_df = pd.merge(pe_pb_div_df[['Date', 'P/E', 'P/B', 'Div Yield %']],
                         pr_df[['Date', 'Close']],
                         on='Date',
                         how='inner')

    # Set 'Date' as index for time series operations
    merged_df = merged_df.set_index('Date')

    # Ensure the merged_df is sorted by date index
    merged_df = merged_df.sort_index()


    # --- Return Calculation for All Daily Investments (3-year Annualized Returns) ---
    print("\n--- Daily Investment 3-Year Annualized Returns ---")

    returns_df = pd.DataFrame() # Initialize an empty DataFrame
    if not merged_df.empty:
        returns_list = []
        # Iterate through each daily entry to calculate 3-year annualized returns
        for index, row in merged_df.iterrows():
            investment_date = index
            investment_pe = row['P/E']
            buy_price = row['Close']

            # Calculate target date 3 years from investment date
            target_date = investment_date + pd.DateOffset(years=3)

            # Find the close price at or after the target_date
            # Get data from the merged_df DataFrame from the target date onwards
            # Use .iloc[0] to get the first available price at or after 3 years
            future_data = merged_df.loc[merged_df.index >= target_date]

            if not future_data.empty and buy_price > 0: # Ensure future data exists and buy_price is valid
                sell_price = future_data['Close'].iloc[0]

                # Calculate the exact number of years for CAGR calculation
                # This makes the annualized return more accurate if the exact 3-year mark isn't found
                delta_years = (future_data.index[0] - investment_date).days / 365.25 # Account for leap years

                try:
                    # Calculate Compound Annual Growth Rate (CAGR)
                    if delta_years > 0 and buy_price > 0:
                        annualized_return_percentage = ((sell_price / buy_price)**(1/delta_years) - 1) * 100
                    else:
                        annualized_return_percentage = float('nan') # Cannot calculate if time delta is zero or buy_price is zero

                    returns_list.append({
                        'Investment Date': investment_date.strftime('%Y-%m-%d'),
                        'P/E at Investment': investment_pe,
                        '3-year Return (% pa)': annualized_return_percentage
                    })
                except ZeroDivisionError:
                    returns_list.append({
                        'Investment Date': investment_date.strftime('%Y-%m-%d'),
                        'P/E at Investment': investment_pe,
                        '3-year Return (% pa)': float('nan')
                    })
            else:
                returns_list.append({
                    'Investment Date': investment_date.strftime('%Y-%m-%d'),
                    'P/E at Investment': investment_pe,
                    '3-year Return (% pa)': float('nan') # No 3-year data available
                })

        # Create DataFrame and drop rows where 3-year return could not be calculated
        returns_df = pd.DataFrame(returns_list).dropna(subset=['3-year Return (% pa)'])

        # Display the returns table (only showing a sample due to large number of rows)
        if not returns_df.empty:
            print("Sample of calculated 3-year annualized returns:")
            print(returns_df.head().to_string(index=False))
            print(f"\n... (and {len(returns_df) - returns_df.head().shape[0]} more rows)")
            print(f"\nNote: 3-year returns are calculated as compound annual growth rate (CAGR) for each daily point.")
        else:
            print("No valid daily data found to calculate returns.")
    else:
        print("No valid daily data found to calculate returns.")


    # --- Generating Scatter Plot: P/E at Investment vs. 3-year Returns ---
    if not returns_df.empty:
        print("\n--- Generating Scatter Plot: P/E at Investment vs. 3-year Returns ---")
        fig_scatter, ax_scatter = plt.subplots(figsize=(10, 7))

        # Use a slightly darker green for points and a bit more transparency for density
        ax_scatter.scatter(returns_df['P/E at Investment'],
                           returns_df['3-year Return (% pa)'],
                           alpha=0.6, color='#28a745', s=25, edgecolor='gray', linewidth=0.2) # Adjusted color and edge

        ax_scatter.set_title('NIFTY NEXT 50: P/E & 3-year Return', fontsize=18, fontweight='bold', pad=20) # Larger, bold title
        ax_scatter.set_xlabel('P/E Ratio', fontsize=14, labelpad=15) # Larger labels
        ax_scatter.set_ylabel('3-year Return (% pa)', fontsize=14, labelpad=15) # Larger labels

        ax_scatter.grid(True, linestyle=':', alpha=0.7, color='lightgray') # Dotted grid lines
        ax_scatter.set_facecolor('#fdfdfd') # Lighter background

        # Add the horizontal line with a more prominent color and text
        ax_scatter.axhline(y=11, color='#dc3545', linestyle='--', linewidth=2.5, label='Average Return (Approx. 11%)') # Dashed line, darker red
        ax_scatter.legend(loc='upper right', fontsize=10, frameon=True, fancybox=True, shadow=True, borderpad=0.8) # Legend styling

        # Add minor ticks for better readability on axes
        ax_scatter.minorticks_on()
        ax_scatter.tick_params(axis='both', which='major', labelsize=10)
        ax_scatter.tick_params(axis='both', which='minor', labelsize=8)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust layout to make space for suptitle if needed
        plt.show()
    else:
        print("Not enough data to generate scatter plot.")


    # --- Plotting P/E and P/B Ratios (original plot) ---
    print("\n--- Generating P/E and P/B Plot ---")

    # Create the figure and a primary axes object
    fig, ax1 = plt.subplots(figsize=(14, 7)) # Adjust figure size for better readability

    # Set background color for the plot area for better contrast
    ax1.set_facecolor('#f0f0f0')

    # Plot PE Ratio on the primary y-axis (ax1)
    # Add a thicker line and markers for clarity
    line1, = ax1.plot(merged_df.index, merged_df['P/E'],
                      color='#1f77b4', linestyle='-', linewidth=2, label='NIFTY NEXT 50 P/E') # Default blue
    ax1.set_xlabel('Date', fontsize=12, labelpad=10) # Add padding to label
    ax1.set_ylabel('P/E Ratio', color='#1f77b4', fontsize=12, labelpad=10)
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.grid(True, linestyle='--', alpha=0.6, color='gray') # Improve grid visibility

    # Create a secondary y-axis (ax2) that shares the same x-axis
    ax2 = ax1.twinx()
    # Plot PB Ratio on the secondary y-axis (ax2)
    line2, = ax2.plot(merged_df.index, merged_df['P/B'],
                      color='#d62728', linestyle='-', linewidth=2, label='NIFTY NEXT 50 P/B') # Default red
    ax2.set_ylabel('P/B Ratio', color='#d62728', fontsize=12, labelpad=10)
    ax2.tick_params(axis='y', labelcolor='#d62728')

    # Set a more descriptive title for the plot
    plt.title('NIFTY NEXT 50: Historical P/E and P/B Ratios', fontsize=16, pad=20)
    plt.suptitle('Data from 01/06/2001 to 20/06/2025', fontsize=10, color='gray')

    # Format x-axis to show dates clearly and avoid overlapping labels
    ax1.xaxis.set_major_locator(mdates.YearLocator(base=2)) # Show every 2 years
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m')) # Format as Year-Month
    plt.xticks(rotation=45, ha='right') # Rotate and align labels

    # Add a unified legend for both lines with improved aesthetics
    lines = [line1, line2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', fontsize=10, frameon=True, fancybox=True, shadow=True, borderpad=0.8)

    # Improve overall layout and add padding
    fig.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust layout to make space for suptitle

    # Display the plot
    plt.show()

except Exception as e:
    print(f"An error occurred: {e}")
    print("Please ensure the CSV files are correctly uploaded and accessible.")
    print(f"Expected file names: {pe_pb_div_file_name}, {pr_file_name}")

