# 📊 Stock/Index Analysis Dashboard

A modern web dashboard engineered for the insightful analysis of Indian stock indices and their constituent stocks, leveraging popular technical indicators such as the Simple Moving Average (SMA).

Built with the robust Flask framework, the efficient `yfinance` library, the powerful `pandas` data manipulation tool, and the versatile `matplotlib` for visualization, this dashboard boasts a clean and responsive user interface enhanced with searchable Select2 dropdowns.

## ✨ Features

* **Index Selection:** Seamlessly choose from major Indian indices: **Nifty 50**, **Bank Nifty**, and **Sensex**.
* **Individual Stock Selection:** Dynamically select individual stocks that are constituents of the chosen index.
* **Historical Price Charts with SMA:** Visualize historical price movements with overlaid **20-day SMA** and **50-day SMA** for trend identification.
* **Buy/Sell Signal Indicators:** Gain potential trading insights with visual buy and sell signals generated based on **SMA crossover events**.
* **Responsive & User-Friendly UI:** Enjoy a clean, intuitive, and responsive interface that adapts gracefully to various screen sizes.
* **Searchable Dropdowns:** Utilize the power of Select2 for efficient and easy selection of indices and stocks.
* **API Key Independence:** No need for cumbersome API key management – the application fetches data directly from Yahoo Finance via the `yfinance` library.

## ⚙️ Installation & Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-project-folder>
    ```

2.  **Create and Activate a Python Virtual Environment (Recommended):**
    * **Windows:**
        ```bash
        python -m venv venv
        venv\Scripts\activate
        ```
    * **macOS/Linux:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

3.  **Install Required Python Packages:**
    * Create a `requirements.txt` file with the following content:
        ```text
        Flask
        yfinance
        pandas
        matplotlib
        numpy
        ```
    * Install the dependencies using pip:
        ```bash
        pip install -r requirements.txt
        ```

4.  **Run the Flask Application:**
    ```bash
    python app.py
    ```

5.  **Open Your Browser:**
    Navigate to:
    ```text
    [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
    ```

## 🖱️ Usage

1.  **Select an Index:** Choose your desired Indian index from the first dropdown menu.
2.  **Select a Stock:** Once an index is selected, the second dropdown will populate with its constituent stocks. Choose the specific stock you wish to analyze.
3.  **Analyze:** Click the "Analyze" button to initiate the data fetching and visualization process. The historical price chart with the SMA overlays will be displayed.
4.  **View Buy/Sell Signals:** Below the generated chart, you will find visual indicators highlighting potential buy and sell signals based on the 20-day SMA crossing above or below the 50-day SMA.

## 📂 File Structure

```text
your-project/
│
├── app.py                # Flask backend with all logic and inline HTML template
├── requirements.txt      # Python dependencies
└── README.md             # This file