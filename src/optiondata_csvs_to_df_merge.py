import pandas as pd
import os


def combine_csv_files(folder_path, data_csv_path):
    dataframes = []

    # Iterate through all files in the specified folder
    for filename in os.listdir(folder_path):
        # Check if the file has a .csv extension
        if filename.endswith('.csv'):
            file_path = os.path.join(folder_path, filename)
            df = pd.read_csv(file_path)
            dataframes.append(df)

    # Concatenate all DataFrames into a single DataFrame
    combined_df = pd.concat(dataframes, ignore_index=True)

    # store df
    combined_df.to_csv(data_csv_path, index=False)

