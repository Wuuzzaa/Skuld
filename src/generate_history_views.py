import re
import os

VIEW_FILES = [
    "db/SQL/views/create_view/FundamentalData.sql",
    "db/SQL/views/create_view/OptionData.sql",
    "db/SQL/views/create_view/OptionDataMerged.sql",
    "db/SQL/views/create_view/OptionPricingMetrics.sql",
    "db/SQL/views/create_view/StockData.sql"
]

OUTPUT_DIR = "db/SQL/views/create_view/history"

KNOWN_TABLES = [
    "FundamentalDataYahoo", "FundamentalDataDividendRadar",
    "OptionDataYahoo", "OptionDataTradingView", "OptionPricingMetrics",
    "StockPrice", "EarningDates", "AnalystPriceTargets",
    "OptionData", "FundamentalData", "StockData", "TechnicalIndicators",
    "OptionDataMerged"
]

def transform_sql(sql_content):
    # 1. Update View Name
    # Matches CREATE VIEW Name
    sql_content = re.sub(r'(?i)(CREATE\s+VIEW\s+)(\w+)', r'\1\2History', sql_content)
    # Matches DROP VIEW IF EXISTS Name
    sql_content = re.sub(r'(?i)(DROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?)(\w+)', r'\1\2History', sql_content)

    # 2. Update Table Names to History Versions
    # We sort by length descending to avoid replacing substrings (e.g. OptionData vs OptionDataYahoo)
    # though \b boundary handles most, specific prefixes matter.
    for table in sorted(KNOWN_TABLES, key=len, reverse=True):
        # We look for the table name ensuring it's not already suffixed by History 
        # (in case of re-runs or overlapping names if simplistic)
        # Regex: \bTable\b(?!History)
        pattern = re.compile(r'(?i)\b' + re.escape(table) + r'\b(?!History)')
        sql_content = pattern.sub(f"{table}History", sql_content)

    # 3. Inject 'date' into SELECT statements
    # We look for SELECT. We scan ahead to see if the first column uses 'a.'.
    # If yes, we inject 'a.date, '. Else we inject 'date, '.
    
    transformed_sql = ""
    last_pos = 0
    # Find all SELECTs
    for match in re.finditer(r'(?i)SELECT\s+', sql_content):
        transformed_sql += sql_content[last_pos:match.end()]
        
        # Check what comes next (ignore whitespace/comments)
        remaining = sql_content[match.end():]
        # Regex to find first token, anchored to start
        # Matches: whitespace/comments, then word, then dot.
        # \s* includes newlines
        token_match = re.match(r'\s*(?:--.*?\n\s*)*([a-zA-Z0-9_"]+)\.', remaining)
        
        prefix = ""
        if token_match:
            alias = token_match.group(1)
            # Only use 'a' alias if detected, or generic check? 
            if alias.lower() == 'a':
                prefix = "a."
            elif alias.lower() in ['b', 'c', 'd']:
                prefix = "a." # Assumption: a is always primary and available
        
        # Append date column
        transformed_sql += f"\n\t{prefix}date, "
        last_pos = match.end()
    
    transformed_sql += sql_content[last_pos:]
    sql_content = transformed_sql

    # 4. Update JOIN conditions
    
    def join_replacer(match):
        original = match.group(1) # Group 1 is the full JOIN string
        alias = match.group(2)    # Group 2 is the alias
        # If alias is 'a', weird, but ignore.
        if alias and alias.lower() == 'a':
            return original
        
        # Check if condition already has date? (Idempotency)
        if 'date' in original and f'{alias}.date' in original:
            return original
            
        # Append condition
        # We try to append at the end of the match
        return f"{original}\n\tAND a.date = {alias}.date"

    # We apply this regex. Note the lookahead for keywords that end the ON clause.
    # The list of keywords is crucial.
    keywords = r"(?:LEFT|RIGHT|INNER|OUTER|JOIN|WHERE|GROUP|ORDER|LIMIT|\)|;|$)"
    # Regex: JOIN <stuff> [AS] <alias> ON <condition> <lookahead>
    # [\s\S]*? matches table/subquery content non-greedily.
    # (\w+) captures the alias right before ON.
    pattern = re.compile(
        r'(?i)(JOIN\s+[\s\S]*?(?:AS\s+)?(\w+)\s+ON\s+.*?)(?=\s*' + keywords + ')', 
        re.DOTALL
    )
    
    sql_content = pattern.sub(join_replacer, sql_content)
    
    # 5. Handle julianday('now')
    # Replace 'now' with 'a.date' (assuming a is valid in that context)
    sql_content = re.sub(r"julianday\s*\(\s*'now'\s*\)", r"julianday(a.date)", sql_content)

    return sql_content

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    for filepath in VIEW_FILES:
        try:
            with open(filepath, 'r') as f:
                content = f.read()
            
            new_content = transform_sql(content)
            
            filename = os.path.basename(filepath)
            new_filename = filename.replace('.sql', 'History.sql')
            output_path = os.path.join(OUTPUT_DIR, new_filename)
            
            with open(output_path, 'w') as f:
                f.write(new_content)
            
            print(f"Generated {output_path}")
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

if __name__ == "__main__":
    main()
