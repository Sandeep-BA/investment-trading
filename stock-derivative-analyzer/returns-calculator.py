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

    # Sort data by date to ensure proper plotting
    pe_pb_div_df = pe_pb_div_df.sort_values(by='Date')
    pr_df = pr_df.sort_values(by='Date')

    # --- Plotting ---

    # Create the figure and a primary axes object
    fig, ax1 = plt.subplots(figsize=(14, 7)) # Adjust figure size for better readability

    # Set background color for the plot area for better contrast
    ax1.set_facecolor('#f0f0f0')

    # Plot PE Ratio on the primary y-axis (ax1)
    # Add a thicker line and markers for clarity
    line1, = ax1.plot(pe_pb_div_df['Date'], pe_pb_div_df['P/E'],
                      color='#1f77b4', linestyle='-', linewidth=2, label='NIFTY NEXT 50 P/E')
    ax1.set_xlabel('Date', fontsize=12, labelpad=10) # Add padding to label
    ax1.set_ylabel('P/E Ratio', color='#1f77b4', fontsize=12, labelpad=10)
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.grid(True, linestyle='--', alpha=0.6, color='gray') # Improve grid visibility

    # Create a secondary y-axis (ax2) that shares the same x-axis
    ax2 = ax1.twinx()
    # Plot PB Ratio on the secondary y-axis (ax2)
    line2, = ax2.plot(pe_pb_div_df['Date'], pe_pb_div_df['P/B'],
                      color='#d62728', linestyle='-', linewidth=2, label='NIFTY NEXT 50 P/B')
    ax2.set_ylabel('P/B Ratio', color='#d62728', fontsize=12, labelpad=10)
    ax2.tick_params(axis='y', labelcolor='#d62728')

    # Set a more descriptive title for the plot
    plt.title('NIFTY NEXT 50: Historical P/E and P/B Ratios', fontsize=16, pad=20)
    plt.suptitle('Data from 01/06/2001 to 20/06/2025', fontsize=10, color='gray')

    # Format x-axis to show dates clearly and avoid overlapping labels
    ax1.xaxis.set_major_locator(mdates.YearLocator(base=2)) # Show every 2 years
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m')) # Format as Year-Month
    plt.xticks(rotation=45, ha='right') # Rotate and align labels

    # Add a unified legend for both lines
    lines = [line1, line2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', frameon=True, fancybox=True, shadow=True, borderpad=1)

    # Improve overall layout and add padding
    fig.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust layout to make space for suptitle

    # Display the plot
    plt.show()

except Exception as e:
    print(f"An error occurred: {e}")
    print("Please ensure the CSV files are correctly uploaded and accessible.")
    print(f"Expected file names: {pe_pb_div_file_name}, {pr_file_name}")

