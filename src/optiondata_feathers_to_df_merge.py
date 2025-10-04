import pandas as pd
import os


def combine_feather_files(folder_path, data_feather_path):
    dataframes = []

    # Iterate through all files in the specified folder
    for filename in os.listdir(folder_path):
        # Check if the file has a .feather extension
        if filename.endswith('.feather'):
            file_path = os.path.join(folder_path, filename)
            df = pd.read_feather(file_path)
            dataframes.append(df)

    # Check if we have any dataframes to concatenate
    if not dataframes:
        print("No .feather files found to combine. Creating empty DataFrame.")
        # Create an empty DataFrame with expected columns for options data
        combined_df = pd.DataFrame(columns=[
            'ask', 'bid', 'delta', 'gamma', 'iv', 'option-type', 'rho', 'strike', 
            'theoPrice', 'theta', 'vega', 'option', 'time', 'symbol', 'exchange', 
            'expiration_date', 'option_osi'
        ])
    else:
        # Concatenate all DataFrames into a single DataFrame
        combined_df = pd.concat(dataframes, ignore_index=True)

    # store df
    combined_df.to_feather(data_feather_path)
    print(f"Combined {len(dataframes)} feather files into {data_feather_path}")

