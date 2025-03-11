import streamlit as st
import pandas as pd

# Titel
st.subheader("Dividenden-Radar")




# Beispielhafter DataFrame aus dem Session State laden
df = st.session_state["df"]

# Hilfsfunktion für die Chowder-Filter
def chowder_filter(data):
    # Bedingung definieren:
    #  (DivYield >= 3 und Chowder > 14) ODER (DivYield < 3 und Chowder > 15)
    condition = (
        ((data["Div Yield"] >= 3) & (data["Chowder Number"] > 14)) |
        ((data["Div Yield"] < 3) & (data["Chowder Number"] > 15))
    )
    return data[condition]

# Session-State-Variable, um zu speichern, ob der Filter aktiv ist
if "chowder_filter_on" not in st.session_state:
    st.session_state["chowder_filter_on"] = False

st.subheader("Total DataFrame")

# Button, um den Filter ein- bzw. auszuschalten
if st.button("Chowder-Filter umschalten"):
    st.session_state["chowder_filter_on"] = not st.session_state["chowder_filter_on"]

# Abhängig vom Zustand im Session State DataFrame anzeigen
if st.session_state["chowder_filter_on"]:
    st.write("**Gefilterter DataFrame** (Chowder-Regeln)")
    df_filtered = chowder_filter(df)
    st.dataframe(df_filtered, use_container_width=True)
else:
    st.write("**Originaler (ungefilterter) DataFrame**")
    st.dataframe(df, use_container_width=True)