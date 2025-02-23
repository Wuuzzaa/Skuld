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

    # Concatenate all DataFrames into a single DataFrame
    combined_df = pd.concat(dataframes)

    # store df
    combined_df.to_feather(data_feather_path)

