import yfinance as yf
import pandas as pd
import numpy as np
import warnings

# Suppress yfinance timezone warnings
warnings.filterwarnings('ignore', category=FutureWarning)

def scan_darvas_breakouts(ticker, box_length=5, target_date=None):
    try:
        stock = yf.Ticker(ticker)
        # Increased period to 1 year to ensure we have data if checking past dates
        df = stock.history(period="1y")
        
        if df.empty or len(df) < box_length + 2:
            return None
            
        # Strip timezone info and normalize the time so we can easily search by YYYY-MM-DD
        df.index = df.index.tz_localize(None).normalize()
        
        # 1. Calculate Standard Rolling High and Low
        df['HH5'] = df['High'].rolling(window=box_length).max()
        df['LL5'] = df['Low'].rolling(window=box_length).min()
        
        # 2. Identify if new lows are being made
        df['Is_New_Low'] = (df['Low'] == df['LL5'])
        df['New_Low_In_Last_5'] = df['Is_New_Low'].rolling(window=box_length).max().fillna(1).astype(bool)
        
        # 3. Calculate the Dynamic Box Top using your specific rules
        box_tops = []
        prev_bt = np.nan
        
        for i in range(len(df)):
            hh5 = df['HH5'].iloc[i]
            has_new_low = df['New_Low_In_Last_5'].iloc[i]
            
            if pd.isna(hh5):
                bt = np.nan
            elif pd.isna(prev_bt):
                bt = hh5
            else:
                if has_new_low:
                    # RULE: As long as new lows are being made in the last 5 days,
                    # the Box Top CANNOT shift down.
                    bt = max(prev_bt, hh5)
                else:
                    # RULE: No new lows in the last 5 days! 
                    # The Box Top is allowed to shift down to the recent 5-day high.
                    bt = hh5
                    
            box_tops.append(bt)
            prev_bt = bt
            
        df['Box_Top_EOD'] = box_tops
        
        # 4. Shift to avoid Look-Ahead Bias
        df['Box_Top'] = df['Box_Top_EOD'].shift(1)
        
        # 5. Detect Breakouts
        df['Bullish_BO'] = (df['Close'] > df['Box_Top']) & (df['Close'].shift(1) <= df['Box_Top'].shift(1))
        
        # 6. Next Day Follow-through / Failure logic
        df['Was_BO_Yesterday'] = df['Bullish_BO'].shift(1).fillna(False)
        df['Bull_Follow_Through'] = df['Was_BO_Yesterday'] & (df['Close'] > df['Close'].shift(1))
        df['Bull_Failed'] = df['Was_BO_Yesterday'] & (df['Close'] < df['Box_Top'].shift(1))
        
        # 7. Select the Target Date
        if target_date:
            target_dt = pd.to_datetime(target_date)
            if target_dt not in df.index:
                print(f"Skipping {ticker}: No data for {target_date} (Market may have been closed).")
                return None
            target_row = df.loc[target_dt]
        else:
            # Default to the most recent trading day if no date is provided
            target_row = df.iloc[-1]
        
        # Return results if any signal triggered on that specific day
        if target_row['Bullish_BO'] or target_row['Bull_Follow_Through'] or target_row['Bull_Failed']:
            return {
                "Date": target_row.name.strftime('%Y-%m-%d'),
                "Ticker": ticker,
                "Close": round(float(target_row['Close']), 2),
                "Box_Top": round(float(target_row['Box_Top']), 2),
                "Bull_BO": bool(target_row['Bullish_BO']),
                "Follow_Through": bool(target_row['Bull_Follow_Through']),
                "Failed_Fakeout": bool(target_row['Bull_Failed'])
            }
            
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
        
    return None

# --- Example Usage ---

universe = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ZOMATO.NS"]
results = []

# You can change this to any specific date (YYYY-MM-DD format)
# Set to None to scan the most recent trading day.
TARGET_DATE = "2024-05-15" 

print(f"Scanning for breakouts on: {TARGET_DATE if TARGET_DATE else 'Latest Day'}")

for stock in universe:
    data = scan_darvas_breakouts(stock, box_length=5, target_date=TARGET_DATE)
    if data:
        results.append(data)

if results:
    results_df = pd.DataFrame(results)
     # Save scan outputs to JSON for the dashboard
    results_df.to_json("scan_results.json", orient="records", date_format="iso")
else:
    print(f"\nNo breakouts, follow-throughs, or failures detected on {TARGET_DATE}.")
