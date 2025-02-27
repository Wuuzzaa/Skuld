from lxml import html
import requests
from urllib.parse import urljoin

# Define the webpage URL
page_url = "https://www.portfolio-insight.com/dividend-radar"
headers = {"User-Agent": "Mozilla/5.0"}

# Send a GET request to the webpage
response = requests.get(page_url, headers=headers)

if response.status_code == 200:
    tree = html.fromstring(response.content)

    # Extract the first XLSX file link using XPath
    file_url = tree.xpath('(//a[contains(@href, ".xlsx")])[1]/@href')

    if file_url:
        file_url = file_url[0]  # Get the first match
        print("Found file URL:", file_url)

        # Convert relative URLs to absolute
        if file_url.startswith("/"):
            file_url = urljoin(page_url, file_url)

        # Download the file
        file_response = requests.get(file_url)
        with open("downloaded_file.xlsx", "wb") as file:
            file.write(file_response.content)

        print("File downloaded successfully.")
    else:
        print("No XLSX download link found.")
else:
    print(f"Failed to load webpage. Status code: {response.status_code}")
