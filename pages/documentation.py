import streamlit as st
from pages.documentation_text.jms_doc import *

# Title
st.subheader("Documentation")

# Sidebar for navigation
page = st.sidebar.selectbox("Documentation for...",
        [
                "JMS",
                "Another Metric",
                "More Topics"
        ]
    )

if page == "JMS":
    st.markdown(JMS_DOC)
    st.latex(JMS_FORMULA)
    st.latex(JMS_DETAILS)

elif page == "Another Metric":
    st.markdown("""
    ## Another Metric
    *Documentation for another calculation goes here...*
    """)

elif page == "More Topics":
    st.markdown("""
    ## More Topics
    *Additional documentation topics can be added here...*
    """)
