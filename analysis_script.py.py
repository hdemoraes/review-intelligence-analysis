import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import os
import plotly.express as px
import plotly.graph_objects as go

from src.analyzer import ReviewAnalyzer, enhance_with_ai
from src.report import generate_pdf_report
from src.domain_detect import detect_domain, get_domain_label
from src.theme_discovery import discover_themes, generate_domain_aware_recommendations
from src.aspect_extraction import extract_aspects_with_sentiment
from src.issue_clustering import cluster_issues_by_theme
from src.pain_decomposition import decompose_pain_by_theme, decompose_pain_by_issue
from src.business_flags import add_flags_to_issues

st.set_page_config(
    page_title="Review Intelligence",
    page_icon="🌴",
    layout="wide"
)

st.title("Review Intelligence")
st.markdown("""
Transform customer reviews into actionable marketing insights for any business.
Get sentiment analysis, theme detection, pain points, opportunities, and ready-to-use ad copy.
""")

with st.expander("📖 How to Use", expanded=False):
    st.markdown("""
    **Step 1: Upload Your Reviews**
    - Upload a CSV, Excel (.xlsx), or JSON file with customer reviews
    - Required column: `review_text` (the actual review content)
    - Optional columns: `rating` (1-5), `date`, `source`
    
    **Step 2: Configure Columns**
    - Select which column contains your review text
    - Optionally select rating and date columns if available
    
    **Step 3: Run Analysis**
    - Click "Analyze Reviews" to process your data
    - View insights across the tabs: Insights, Themes, Recommendations, Copy Hooks
    
    **Step 4: Export Results**
    - Download a professional PDF report
    - Export scored CSV with sentiment data
    - Get insights as JSON for further processing
    
    **Optional: AI Enhancement**
    - Toggle on AI enhancement for refined summaries and copy hooks
    - Requires an OpenAI API key
    """)
    
    st.markdown("**Supported File Formats:**")
    st.markdown("- **CSV**: `date,rating,review_text,source`")
    st.markdown("- **Excel (.xlsx)**: Same column structure")
    st.markdown("- **JSON**: Array of objects with same fields")

st.sidebar.header("Configuration")

st.sidebar.subheader("Branding (Optional)")
with st.sidebar.expander("White-Label Settings", expanded=False):
    agency_name = st.text_input("Agency Name", value="", key="agency_name")
    agency_email = st.text_input("Agency Email", value="", key="agency_email")
    agency_phone = st.text_input("Agency Phone", value="", key="agency_phone")
    client_name = st.text_input("Client Name", value="", key="client_name")
    white_label_mode = st.toggle("White-label Mode", value=False, help="Remove app name from report, show Agency Name instead")
    logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"], key="logo_upload")

st.sidebar.markdown("---")
business_name = st.sidebar.text_input("Business Name (required)", value="My Business")

industry_options = ["Hospitality", "Tourism", "Clinic", "Gym", "Trades", "Retail", "Other"]
industry = st.sidebar.selectbox("Industry", industry_options)

st.sidebar.markdown("---")
st.sidebar.subheader("Data Source")

demo_col1, demo_col2 = st.sidebar.columns(2)
with demo_col1:
    load_demo = st.button("Load Demo Data", type="secondary")
with demo_col2:
    clear_data = st.button("Clear Data")

if load_demo:
    if os.path.exists("templates/sample_reviews.csv"):
        st.session_state["demo_df"] = pd.read_csv("templates/sample_reviews.csv")
        st.sidebar.success("Demo data loaded!")
    else:
        st.sidebar.error("Sample file not found")

if clear_data:
    for key in ["demo_df", "metrics", "analyzed_df", "action_plan", "copy_hooks", "executive_summary"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

uploaded_file = st.sidebar.file_uploader("Upload Reviews", type=["csv", "xlsx", "json"])

missing_review_text_col = False
df = None
text_col = None
rating_col = None
date_col = None

if "demo_df" in st.session_state:
    df = st.session_state["demo_df"].copy()
    st.sidebar.success(f"Using demo data: {len(df)} reviews")
    columns = df.columns.tolist()
    default_text_col = "review_text" if "review_text" in columns else columns[0]
    text_col = st.sidebar.selectbox("Review Text Column", columns, index=columns.index(default_text_col) if default_text_col in columns else 0, key="demo_text_col")
    rating_options = ["None"] + columns
    default_rating = "rating" if "rating" in columns else "None"
    rating_col = st.sidebar.selectbox("Rating Column (optional)", rating_options, index=rating_options.index(default_rating) if default_rating in rating_options else 0, key="demo_rating_col")
    if rating_col == "None":
        rating_col = None
    date_options = ["None"] + columns
    default_date = "date" if "date" in columns else "None"
    date_col = st.sidebar.selectbox("Date Column (optional)", date_options, index=date_options.index(default_date) if default_date in date_options else 0, key="demo_date_col")
    if date_col == "None":
        date_col = None

elif uploaded_file is not None:
    try:
        file_extension = uploaded_file.name.split(".")[-1].lower()
        
        if file_extension == "csv":
            df = pd.read_csv(uploaded_file)
        elif file_extension == "xlsx":
            df = pd.read_excel(uploaded_file)
        elif file_extension == "json":
            json_data = json.load(uploaded_file)
            if isinstance(json_data, list):
                df = pd.DataFrame(json_data)
            elif isinstance(json_data, dict) and "reviews" in json_data:
                df = pd.DataFrame(json_data["reviews"])
            else:
                df = pd.DataFrame([json_data])
        
        st.sidebar.success(f"Loaded {len(df)} reviews from {file_extension.upper()}")
        
        columns = df.columns.tolist()
        
        if "review_text" not in columns:
            missing_review_text_col = True
            st.sidebar.error("Missing required 'review_text' column!")
        
        default_text_col = "review_text" if "review_text" in columns else columns[0]
        text_col = st.sidebar.selectbox("Review Text Column", columns, index=columns.index(default_text_col) if default_text_col in columns else 0)
        
        rating_options = ["None"] + columns
        default_rating = "rating" if "rating" in columns else "None"
        rating_col = st.sidebar.selectbox("Rating Column (optional)", rating_options, index=rating_options.index(default_rating) if default_rating in rating_options else 0)
        if rating_col == "None":
            rating_col = None
        
        date_options = ["None"] + columns
        default_date = "date" if "date" in columns else "None"
        date_col = st.sidebar.selectbox("Date Column (optional)", date_options, index=date_options.index(default_date) if default_date in date_options else 0)
        if date_col == "None":
            date_col = None
        
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")
        df = None
        text_col = None
        rating_col = None
        date_col = None

st.sidebar.markdown("---")
st.sidebar.subheader("AI Enhancement")
use_ai = st.sidebar.toggle("Use AI Enhancement (optional)", value=False)

api_key = None
if use_ai:
    api_key = st.sidebar.text_input("OpenAI API Key", type="password")
    st.sidebar.caption("AI will refine the executive summary and copy hooks")

if "custom_framework" not in st.session_state:
    st.session_state["custom_framework"] = None

if df is not None:
    st.subheader("Data Preview")
    st.dataframe(df.head(10), use_container_width=True)
    
    if missing_review_text_col:
        st.error("""
**Missing Required Column: `review_text`**

Your file must contain a column named `review_text` with the customer review content.

**Required Format:**
- CSV: `date,rating,review_text,source`
- Excel: Same column structure
- JSON: `[{"review_text": "...", "rating": 5, ...}]`

**How to fix:**
1. Open your file in a spreadsheet application
2. Rename your review column to `review_text`
3. Save and re-upload the file

Or, select your review column from the dropdown in the sidebar.
        """)
    elif text_col not in df.columns:
        st.error(f"Column '{text_col}' not found in your file. Please select the correct review text column.")
    else:
        if st.button("🔍 Analyze Reviews", type="primary"):
            with st.spinner("Analyzing reviews..."):
                custom_framework = st.session_state.get("custom_framework")
                if custom_framework:
                    analyzer = ReviewAnalyzer(framework_path=None)
                    analyzer.framework = custom_framework
                    analyzer.themes = custom_framework.get("themes", {})
                    analyzer.severity_keywords = custom_framework.get("scoring", {}).get("severity_keywords", {})
                else:
                    analyzer = ReviewAnalyzer()
                
                analyzed_df = analyzer.analyze_reviews(df, text_col, rating_col)
                
                if date_col and date_col in analyzed_df.columns:
                    try:
                        analyzed_df["parsed_date"] = pd.to_datetime(analyzed_df[date_col], errors='coerce')
                    except:
                        analyzed_df["parsed_date"] = None
                
                metrics = analyzer.compute_metrics(analyzed_df)
                
                action_plan = analyzer.generate_action_plan(metrics)
                copy_hooks = analyzer.generate_copy_hooks(metrics)
                
                executive_summary = analyzer.generate_executive_summary(metrics, business_name)
                
                top_pos_theme = metrics.get("top_positive_theme")
                top_neg_theme = metrics.get("top_negative_theme")
                
                top_positive_quotes = []
                top_negative_quotes = []
                
                if top_pos_theme:
                    top_positive_quotes = analyzer.get_top_quotes(analyzed_df, text_col, top_pos_theme, "positive")
                if top_neg_theme:
                    top_negative_quotes = analyzer.get_top_quotes(analyzed_df, text_col, top_neg_theme, "negative")
                
                top_3_positive = metrics.get("top_3_positive_themes", [])
                top_3_negative = metrics.get("top_3_negative_themes", [])
                grouped_positive_quotes = analyzer.get_grouped_quotes(analyzed_df, text_col, top_3_positive, "positive")
                grouped_negative_quotes = analyzer.get_grouped_quotes(analyzed_df, text_col, top_3_negative, "negative")
                
                quick_wins = analyzer.generate_quick_wins(metrics)
                ops_fixes = analyzer.generate_ops_fixes(metrics)
                copy_hooks_extended = analyzer.generate_copy_hooks_extended(metrics)
                
                if use_ai and api_key:
                    with st.spinner("Enhancing with AI..."):
                        ai_summary, ai_hooks = enhance_with_ai(api_key, metrics, copy_hooks, business_name)
                        if ai_summary:
                            executive_summary = ai_summary
                        if ai_hooks:
                            copy_hooks = ai_hooks
                
                st.session_state["analyzed_df"] = analyzed_df
                st.session_state["metrics"] = metrics
                st.session_state["action_plan"] = action_plan
                st.session_state["copy_hooks"] = copy_hooks
                st.session_state["executive_summary"] = executive_summary
                st.session_state["top_positive_quotes"] = top_positive_quotes
                st.session_state["top_negative_quotes"] = top_negative_quotes
                st.session_state["analyzer"] = analyzer
                st.session_state["text_col"] = text_col
                st.session_state["date_col"] = date_col
                st.session_state["business_name"] = business_name
                st.session_state["quick_wins"] = quick_wins
                st.session_state["ops_fixes"] = ops_fixes
                st.session_state["copy_hooks_extended"] = copy_hooks_extended
                st.session_state["grouped_positive_quotes"] = grouped_positive_quotes
                st.session_state["grouped_negative_quotes"] = grouped_negative_quotes
                
                texts_for_domain = df[text_col].dropna().astype(str).tolist()
                domain_result = detect_domain(texts_for_domain)
                st.session_state["domain_result"] = domain_result
                
                discovered_themes = discover_themes(df, text_col)
                st.session_state["discovered_themes"] = discovered_themes
                
                neg_ratio = metrics.get("negative_count", 0) / max(len(analyzed_df), 1)
                domain_recommendations = generate_domain_aware_recommendations(
                    discovered_themes,
                    domain_result.get("domain", "other"),
                    neg_ratio
                )
                st.session_state["domain_recommendations"] = domain_recommendations
                
            st.success("Analysis complete!")

if "metrics" in st.session_state:
    metrics = st.session_state["metrics"]
    analyzed_df = st.session_state["analyzed_df"]
    action_plan = st.session_state["action_plan"]
    copy_hooks = st.session_state["copy_hooks"]
    executive_summary = st.session_state["executive_summary"]
    top_positive_quotes = st.session_state["top_positive_quotes"]
    top_negative_quotes = st.session_state["top_negative_quotes"]
    analyzer = st.session_state["analyzer"]
    text_col = st.session_state["text_col"]
    date_col_stored = st.session_state.get("date_col")
    business_name = st.session_state["business_name"]
    themes = analyzer.themes
    
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "📊 Insights", "🏷️ Themes", "📋 Recommendations", "✍️ Copy Hooks", 
        "📈 Interactive Charts", "🔄 Comparative Analysis", "⚙️ Theme Editor", "📥 Export"
    ])
    
    with tab1:
        domain_result = st.session_state.get("domain_result", {})
        detected_domain = domain_result.get("domain", "other")
        domain_confidence = domain_result.get("confidence", 0)
        total_hits = domain_result.get("total_hits", 0)
        domain_label = get_domain_label(detected_domain)
        
        st.subheader("Detected Domain")
        domain_col1, domain_col2 = st.columns([2, 3])
        with domain_col1:
            st.metric("Business Type", domain_label)
        with domain_col2:
            st.metric("Confidence", f"{domain_confidence:.0%}")
        
        if total_hits < 20:
            st.info("Insufficient domain signals in dataset. Generic analysis applied. Insights and quotes are reliable.")
        elif detected_domain == "other" or domain_confidence < 0.5:
            st.warning("Domain detection inconclusive. Recommendations may be limited. Insights and quotes are still reliable.")
        
        st.markdown("---")
        
        st.subheader("Executive Summary")
        st.info(executive_summary)
        
        st.subheader("Key Metrics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Overall Sentiment Score", f"{metrics['overall_sentiment_score']}%")
        with col2:
            st.metric("Pain Index", f"{metrics['pain_index']}")
        with col3:
            st.metric("Opportunity Index", f"{metrics['opportunity_index']}")
        with col4:
            total = metrics['positive_count'] + metrics['neutral_count'] + metrics['negative_count']
            st.metric("Total Reviews", total)
        
        st.subheader("Sentiment Distribution")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Positive", metrics['positive_count'], delta=None)
        with col2:
            st.metric("Neutral", metrics['neutral_count'], delta=None)
        with col3:
            st.metric("Negative", metrics['negative_count'], delta=None)
        
        fig = px.pie(
            values=[metrics['positive_count'], metrics['neutral_count'], metrics['negative_count']],
            names=['Positive', 'Neutral', 'Negative'],
            color_discrete_sequence=['#28a745', '#ffc107', '#dc3545'],
            title='Sentiment Distribution'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Top Quotes")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Top Positive Quotes:**")
            if top_positive_quotes:
                for quote in top_positive_quotes:
                    st.success(f'"{quote}"')
            else:
                st.write("No positive quotes found.")
        with col2:
            st.markdown("**Top Negative Quotes:**")
            if top_negative_quotes:
                for quote in top_negative_quotes:
                    st.error(f'"{quote}"')
            else:
                st.write("No negative quotes found.")
    
    with tab2:
        st.subheader("Theme Analysis")
        
        discovered_themes = st.session_state.get("discovered_themes", [])
        if discovered_themes:
            st.markdown("**Discovered Themes** (auto-detected from your data):")
            disc_theme_data = []
            for theme in discovered_themes:
                disc_theme_data.append({
                    "Theme": theme.get("theme", "Unknown"),
                    "Support": f"{theme.get('support', 0):.1%}",
                    "Keywords": ", ".join(theme.get("keywords", [])[:5])
                })
            st.dataframe(pd.DataFrame(disc_theme_data), use_container_width=True)
            st.markdown("---")
        
        st.markdown("**Framework Themes** (rule-based analysis):")
        theme_scores = metrics.get("theme_impact_scores", {})
        
        theme_data = []
        for theme_key, score in sorted(theme_scores.items(), key=lambda x: x[1], reverse=True):
            theme_info = themes.get(theme_key, {})
            theme_data.append({
                "Theme": theme_info.get("label", theme_key),
                "Impact Score": score,
                "Business Impact": theme_info.get("business_impact", "N/A"),
                "Marketing Angle": theme_info.get("marketing_angle", "N/A")
            })
        
        theme_df = pd.DataFrame(theme_data)
        st.dataframe(theme_df, use_container_width=True)
        
        sorted_themes = sorted(theme_scores.items(), key=lambda x: x[1], reverse=True)
        labels = [themes.get(t, {}).get('label', t)[:20] for t, _ in sorted_themes]
        values = [v for _, v in sorted_themes]
        colors = ['#28a745' if v >= 0 else '#dc3545' for v in values]
        
        fig = go.Figure(go.Bar(
            x=values,
            y=labels,
            orientation='h',
            marker_color=colors
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="gray")
        fig.update_layout(title='Theme Impact Scores', xaxis_title='Impact Score', yaxis_title='Theme')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Action Plan (Next 14 Days)")
        
        domain_recommendations = st.session_state.get("domain_recommendations", {})
        has_high_confidence = domain_recommendations.get("has_high_confidence", False)
        recommendations_list = domain_recommendations.get("recommendations", [])
        
        if has_high_confidence and recommendations_list:
            st.markdown("Based on the analysis, here are recommended actions to address key issues:")
            
            action_count = 0
            for rec in recommendations_list:
                if rec.get("guardrail_status") == "passed" and rec.get("actions"):
                    theme_name = rec.get("theme", "Unknown")
                    st.markdown(f"**{theme_name}** (Confidence: {rec.get('confidence', 0):.0%})")
                    for action in rec.get("actions", []):
                        action_count += 1
                        st.markdown(f"{action_count}. {action}")
                    st.markdown("")
            
            if action_count == 0:
                st.info("No high-confidence recommendations available. Showing rule-based actions:")
                for i, action in enumerate(action_plan, 1):
                    st.markdown(f"**{i}.** {action}")
        else:
            st.info("No high-confidence recommendations. Showing insights and quotes only.")
            st.markdown("*Recommendations require sufficient data and clear theme patterns.*")
            
            if recommendations_list:
                st.markdown("**Discovered Themes (for reference):**")
                for rec in recommendations_list[:5]:
                    theme_name = rec.get("theme", "Unknown")
                    support = rec.get("support", 0)
                    status = rec.get("guardrail_status", "unknown")
                    reason = rec.get("guardrail_reason", "")
                    st.markdown(f"- {theme_name} ({support:.1%} support) - *{reason}*")
        
        st.markdown("---")
        st.subheader("Key Issues to Address")
        
        top_neg = metrics.get("top_negative_theme")
        if top_neg:
            neg_label = themes.get(top_neg, {}).get("label", top_neg)
            neg_angle = themes.get(top_neg, {}).get("marketing_angle", "Address customer concerns")
            st.warning(f"**Primary Issue:** {neg_label}")
            st.info(f"**Marketing Approach:** {neg_angle}")
        else:
            st.success("No significant negative themes detected!")
    
    with tab4:
        st.subheader("Marketing Copy Hooks")
        st.markdown("Use these headlines in your advertising and marketing materials:")
        
        for i, hook in enumerate(copy_hooks, 1):
            st.markdown(f"**{i}.** {hook}")
        
        st.markdown("---")
        st.subheader("Leverage Your Strengths")
        
        top_pos = metrics.get("top_positive_theme")
        if top_pos:
            pos_label = themes.get(top_pos, {}).get("label", top_pos)
            pos_angle = themes.get(top_pos, {}).get("marketing_angle", "Highlight your strengths")
            st.success(f"**Top Strength:** {pos_label}")
            st.info(f"**Marketing Approach:** {pos_angle}")
    
    with tab5:
        st.subheader("Interactive Visualizations")
        st.markdown("Filter and explore your review data interactively.")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            sentiment_filter = st.multiselect(
                "Filter by Sentiment",
                options=["positive", "neutral", "negative"],
                default=["positive", "neutral", "negative"]
            )
        
        with filter_col2:
            all_themes_list = list(themes.keys())
            theme_filter = st.multiselect(
                "Filter by Theme",
                options=all_themes_list,
                default=[],
                format_func=lambda x: themes.get(x, {}).get("label", x)
            )
        
        with filter_col3:
            if "parsed_date" in analyzed_df.columns and analyzed_df["parsed_date"].notna().any():
                min_date = analyzed_df["parsed_date"].min()
                max_date = analyzed_df["parsed_date"].max()
                if pd.notna(min_date) and pd.notna(max_date):
                    date_range = st.date_input(
                        "Date Range",
                        value=(min_date.date(), max_date.date()),
                        min_value=min_date.date(),
                        max_value=max_date.date()
                    )
                else:
                    date_range = None
            else:
                st.info("No date column available for filtering")
                date_range = None
        
        filtered_df = analyzed_df.copy()
        
        if sentiment_filter:
            filtered_df = filtered_df[filtered_df["sentiment"].isin(sentiment_filter)]
        
        if theme_filter:
            theme_mask = filtered_df["matched_themes"].apply(
                lambda x: any(t in str(x) for t in theme_filter) if pd.notna(x) else False
            )
            filtered_df = filtered_df[theme_mask]
        
        if date_range and "parsed_date" in filtered_df.columns and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df["parsed_date"].dt.date >= start_date) & 
                (filtered_df["parsed_date"].dt.date <= end_date)
            ]
        
        st.markdown(f"**Showing {len(filtered_df)} of {len(analyzed_df)} reviews**")
        
        viz_col1, viz_col2 = st.columns(2)
        
        with viz_col1:
            sentiment_counts = filtered_df["sentiment"].value_counts()
            fig_sentiment = px.pie(
                values=sentiment_counts.values,
                names=sentiment_counts.index,
                title="Sentiment Distribution (Filtered)",
                color=sentiment_counts.index,
                color_discrete_map={"positive": "#28a745", "neutral": "#ffc107", "negative": "#dc3545"}
            )
            st.plotly_chart(fig_sentiment, use_container_width=True)
        
        with viz_col2:
            severity_counts = filtered_df["severity"].value_counts()
            fig_severity = px.bar(
                x=severity_counts.index,
                y=severity_counts.values,
                title="Severity Distribution (Filtered)",
                color=severity_counts.index,
                color_discrete_map={"high": "#dc3545", "medium": "#ffc107", "low": "#28a745"}
            )
            fig_severity.update_layout(xaxis_title="Severity", yaxis_title="Count")
            st.plotly_chart(fig_severity, use_container_width=True)
        
        if "parsed_date" in filtered_df.columns and filtered_df["parsed_date"].notna().any():
            st.subheader("Sentiment Over Time")
            
            time_df = filtered_df[filtered_df["parsed_date"].notna()].copy()
            time_df["date"] = time_df["parsed_date"].dt.date
            
            sentiment_time = time_df.groupby(["date", "sentiment"]).size().reset_index(name="count")
            
            fig_time = px.line(
                sentiment_time,
                x="date",
                y="count",
                color="sentiment",
                title="Sentiment Trends Over Time",
                color_discrete_map={"positive": "#28a745", "neutral": "#ffc107", "negative": "#dc3545"}
            )
            st.plotly_chart(fig_time, use_container_width=True)
        
        st.subheader("Theme Distribution")
        theme_counts = {}
        for _, row in filtered_df.iterrows():
            if pd.notna(row["matched_themes"]) and row["matched_themes"]:
                for theme in str(row["matched_themes"]).split(", "):
                    theme = theme.strip()
                    if theme:
                        theme_counts[theme] = theme_counts.get(theme, 0) + 1
        
        if theme_counts:
            theme_labels = [themes.get(t, {}).get("label", t) for t in theme_counts.keys()]
            fig_themes = px.bar(
                x=theme_labels,
                y=list(theme_counts.values()),
                title="Theme Frequency (Filtered)",
                color=list(theme_counts.values()),
                color_continuous_scale="Blues"
            )
            fig_themes.update_layout(xaxis_title="Theme", yaxis_title="Count", showlegend=False)
            st.plotly_chart(fig_themes, use_container_width=True)
        
        st.subheader("Filtered Reviews")
        display_cols = [text_col, "sentiment", "severity", "matched_themes"]
        if date_col_stored:
            display_cols.insert(0, date_col_stored)
        available_cols = [c for c in display_cols if c in filtered_df.columns]
        st.dataframe(filtered_df[available_cols].head(50), use_container_width=True)
    
    with tab6:
        st.subheader("Comparative Analysis")
        st.markdown("Compare review data across different time periods or upload a second dataset for comparison.")
        
        compare_option = st.radio(
            "Comparison Type",
            ["Time Period Comparison", "Dataset Comparison"],
            horizontal=True
        )
        
        if compare_option == "Time Period Comparison":
            if "parsed_date" in analyzed_df.columns and analyzed_df["parsed_date"].notna().any():
                st.markdown("**Define two time periods to compare:**")
                
                min_date = analyzed_df["parsed_date"].min()
                max_date = analyzed_df["parsed_date"].max()
                mid_date = min_date + (max_date - min_date) / 2
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Period 1 (Earlier)**")
                    period1_start = st.date_input("Start Date (Period 1)", value=min_date.date(), key="p1_start")
                    period1_end = st.date_input("End Date (Period 1)", value=mid_date.date(), key="p1_end")
                
                with col2:
                    st.markdown("**Period 2 (Later)**")
                    period2_start = st.date_input("Start Date (Period 2)", value=mid_date.date(), key="p2_start")
                    period2_end = st.date_input("End Date (Period 2)", value=max_date.date(), key="p2_end")
                
                if st.button("Compare Periods", type="primary"):
                    period1_df = analyzed_df[
                        (analyzed_df["parsed_date"].dt.date >= period1_start) & 
                        (analyzed_df["parsed_date"].dt.date <= period1_end)
                    ]
                    period2_df = analyzed_df[
                        (analyzed_df["parsed_date"].dt.date >= period2_start) & 
                        (analyzed_df["parsed_date"].dt.date <= period2_end)
                    ]
                    
                    if len(period1_df) == 0 or len(period2_df) == 0:
                        st.error("One or both periods have no data. Please adjust the date ranges.")
                    else:
                        metrics1 = analyzer.compute_metrics(period1_df)
                        metrics2 = analyzer.compute_metrics(period2_df)
                        
                        st.markdown("### Comparison Results")
                        
                        comp_col1, comp_col2 = st.columns(2)
                        
                        with comp_col1:
                            st.markdown(f"**Period 1** ({period1_start} to {period1_end})")
                            st.metric("Reviews", len(period1_df))
                            st.metric("Sentiment Score", f"{metrics1['overall_sentiment_score']}%")
                            st.metric("Pain Index", metrics1['pain_index'])
                            st.metric("Opportunity Index", metrics1['opportunity_index'])
                        
                        with comp_col2:
                            st.markdown(f"**Period 2** ({period2_start} to {period2_end})")
                            st.metric("Reviews", len(period2_df))
                            delta_sentiment = metrics2['overall_sentiment_score'] - metrics1['overall_sentiment_score']
                            st.metric("Sentiment Score", f"{metrics2['overall_sentiment_score']}%", delta=f"{delta_sentiment:+.1f}%")
                            delta_pain = metrics2['pain_index'] - metrics1['pain_index']
                            st.metric("Pain Index", metrics2['pain_index'], delta=f"{delta_pain:+.1f}", delta_color="inverse")
                            delta_opp = metrics2['opportunity_index'] - metrics1['opportunity_index']
                            st.metric("Opportunity Index", metrics2['opportunity_index'], delta=f"{delta_opp:+.1f}")
                        
                        comparison_data = {
                            "Metric": ["Sentiment Score", "Positive %", "Negative %", "Pain Index", "Opportunity Index"],
                            "Period 1": [
                                metrics1['overall_sentiment_score'],
                                round(metrics1['positive_count'] / len(period1_df) * 100, 1) if len(period1_df) > 0 else 0,
                                round(metrics1['negative_count'] / len(period1_df) * 100, 1) if len(period1_df) > 0 else 0,
                                metrics1['pain_index'],
                                metrics1['opportunity_index']
                            ],
                            "Period 2": [
                                metrics2['overall_sentiment_score'],
                                round(metrics2['positive_count'] / len(period2_df) * 100, 1) if len(period2_df) > 0 else 0,
                                round(metrics2['negative_count'] / len(period2_df) * 100, 1) if len(period2_df) > 0 else 0,
                                metrics2['pain_index'],
                                metrics2['opportunity_index']
                            ]
                        }
                        comparison_df = pd.DataFrame(comparison_data)
                        comparison_df["Change"] = comparison_df["Period 2"] - comparison_df["Period 1"]
                        
                        fig_compare = go.Figure(data=[
                            go.Bar(name='Period 1', x=comparison_data["Metric"], y=comparison_data["Period 1"]),
                            go.Bar(name='Period 2', x=comparison_data["Metric"], y=comparison_data["Period 2"])
                        ])
                        fig_compare.update_layout(barmode='group', title='Period Comparison')
                        st.plotly_chart(fig_compare, use_container_width=True)
            else:
                st.warning("No date column available. Please ensure your data has a date column for time-based comparison.")
        
        else:
            st.markdown("**Upload a second dataset for comparison:**")
            
            compare_file = st.file_uploader("Upload Comparison Dataset", type=["csv", "xlsx", "json"], key="compare_file")
            
            if compare_file:
                try:
                    file_ext = compare_file.name.split(".")[-1].lower()
                    if file_ext == "csv":
                        compare_df_raw = pd.read_csv(compare_file)
                    elif file_ext == "xlsx":
                        compare_df_raw = pd.read_excel(compare_file)
                    else:
                        json_data = json.load(compare_file)
                        compare_df_raw = pd.DataFrame(json_data if isinstance(json_data, list) else json_data.get("reviews", [json_data]))
                    
                    st.success(f"Loaded {len(compare_df_raw)} reviews for comparison")
                    
                    if text_col in compare_df_raw.columns:
                        compare_analyzed = analyzer.analyze_reviews(compare_df_raw, text_col, None)
                        compare_metrics = analyzer.compute_metrics(compare_analyzed)
                        
                        st.markdown("### Dataset Comparison")
                        
                        comp_col1, comp_col2 = st.columns(2)
                        
                        with comp_col1:
                            st.markdown("**Original Dataset**")
                            st.metric("Reviews", len(analyzed_df))
                            st.metric("Sentiment Score", f"{metrics['overall_sentiment_score']}%")
                            st.metric("Pain Index", metrics['pain_index'])
                            st.metric("Opportunity Index", metrics['opportunity_index'])
                        
                        with comp_col2:
                            st.markdown("**Comparison Dataset**")
                            st.metric("Reviews", len(compare_analyzed))
                            delta_s = compare_metrics['overall_sentiment_score'] - metrics['overall_sentiment_score']
                            st.metric("Sentiment Score", f"{compare_metrics['overall_sentiment_score']}%", delta=f"{delta_s:+.1f}%")
                            delta_p = compare_metrics['pain_index'] - metrics['pain_index']
                            st.metric("Pain Index", compare_metrics['pain_index'], delta=f"{delta_p:+.1f}", delta_color="inverse")
                            delta_o = compare_metrics['opportunity_index'] - metrics['opportunity_index']
                            st.metric("Opportunity Index", compare_metrics['opportunity_index'], delta=f"{delta_o:+.1f}")
                    else:
                        st.error(f"Comparison dataset must have '{text_col}' column")
                        
                except Exception as e:
                    st.error(f"Error loading comparison file: {e}")
    
    with tab7:
        st.subheader("Theme Framework Editor")
        st.markdown("Customize the theme framework for different regions or industries.")
        
        editor_mode = st.radio(
            "Editor Mode",
            ["View Current Framework", "Edit Framework", "Create New Framework", "Import/Export"],
            horizontal=True
        )
        
        current_framework = st.session_state.get("custom_framework") or analyzer.framework
        
        if editor_mode == "View Current Framework":
            st.markdown("### Current Theme Configuration")
            
            meta = current_framework.get("meta", {})
            st.markdown(f"**Region:** {meta.get('region', 'Not specified')}")
            st.markdown(f"**Version:** {meta.get('version', '1.0')}")
            st.markdown(f"**Target Business Types:** {', '.join(meta.get('target_business_types', []))}")
            
            st.markdown("### Themes")
            for theme_key, theme_data in current_framework.get("themes", {}).items():
                with st.expander(f"📌 {theme_data.get('label', theme_key)}"):
                    st.markdown(f"**Business Impact:** {theme_data.get('business_impact', 'N/A')}")
                    st.markdown(f"**Marketing Angle:** {theme_data.get('marketing_angle', 'N/A')}")
                    st.markdown(f"**Keywords:** {', '.join(theme_data.get('keywords', []))}")
        
        elif editor_mode == "Edit Framework":
            st.markdown("### Edit Existing Themes")
            
            theme_to_edit = st.selectbox(
                "Select Theme to Edit",
                options=list(current_framework.get("themes", {}).keys()),
                format_func=lambda x: current_framework.get("themes", {}).get(x, {}).get("label", x)
            )
            
            if theme_to_edit:
                theme_data = current_framework.get("themes", {}).get(theme_to_edit, {})
                
                new_label = st.text_input("Theme Label", value=theme_data.get("label", ""))
                new_impact = st.selectbox("Business Impact", ["Critical", "High", "Medium", "Low"], 
                                          index=["Critical", "High", "Medium", "Low"].index(theme_data.get("business_impact", "Medium")))
                new_angle = st.text_input("Marketing Angle", value=theme_data.get("marketing_angle", ""))
                new_keywords = st.text_area("Keywords (one per line)", 
                                            value="\n".join(theme_data.get("keywords", [])))
                
                if st.button("Save Theme Changes"):
                    updated_framework = current_framework.copy()
                    updated_framework["themes"] = updated_framework.get("themes", {}).copy()
                    updated_framework["themes"][theme_to_edit] = {
                        "label": new_label,
                        "business_impact": new_impact,
                        "marketing_angle": new_angle,
                        "keywords": [k.strip() for k in new_keywords.split("\n") if k.strip()]
                    }
                    st.session_state["custom_framework"] = updated_framework
                    st.success("Theme updated! Re-run analysis to apply changes.")
        
        elif editor_mode == "Create New Framework":
            st.markdown("### Create New Theme Framework")
            
            new_region = st.text_input("Region", value="My Region")
            new_business_types = st.text_area("Target Business Types (one per line)", 
                                               value="Hospitality\nRetail\nServices")
            
            st.markdown("### Add New Theme")
            
            new_theme_key = st.text_input("Theme Key (no spaces, lowercase)", value="new_theme")
            new_theme_label = st.text_input("Theme Label", value="New Theme")
            new_theme_impact = st.selectbox("Business Impact", ["Critical", "High", "Medium", "Low"], key="new_impact")
            new_theme_angle = st.text_input("Marketing Angle", value="Highlight this aspect in marketing")
            new_theme_keywords = st.text_area("Keywords (one per line)", value="keyword1\nkeyword2")
            
            if st.button("Create Framework with Theme"):
                new_framework = {
                    "meta": {
                        "region": new_region,
                        "target_business_types": [t.strip() for t in new_business_types.split("\n") if t.strip()],
                        "version": "1.0"
                    },
                    "scoring": current_framework.get("scoring", {}),
                    "themes": {
                        new_theme_key: {
                            "label": new_theme_label,
                            "business_impact": new_theme_impact,
                            "marketing_angle": new_theme_angle,
                            "keywords": [k.strip() for k in new_theme_keywords.split("\n") if k.strip()]
                        }
                    },
                    "outputs": current_framework.get("outputs", {})
                }
                st.session_state["custom_framework"] = new_framework
                st.success("New framework created! Re-run analysis to apply.")
        
        else:
            st.markdown("### Import/Export Framework")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Export Current Framework**")
                framework_json = json.dumps(current_framework, indent=2)
                st.download_button(
                    label="📥 Download Framework JSON",
                    data=framework_json,
                    file_name="custom_theme_framework.json",
                    mime="application/json"
                )
            
            with col2:
                st.markdown("**Import Framework**")
                import_file = st.file_uploader("Upload Framework JSON", type=["json"], key="import_framework")
                
                if import_file:
                    try:
                        imported = json.load(import_file)
                        if "themes" in imported:
                            st.session_state["custom_framework"] = imported
                            st.success("Framework imported! Re-run analysis to apply.")
                        else:
                            st.error("Invalid framework file: missing 'themes' key")
                    except Exception as e:
                        st.error(f"Error importing framework: {e}")
            
            if st.button("Reset to Default Framework"):
                st.session_state["custom_framework"] = None
                st.success("Reset to default framework. Re-run analysis to apply.")
    
    with tab8:
        st.subheader("Export Your Results")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### PDF Report")
            st.markdown("Download a professional client report")
            
            try:
                logo_bytes = None
                if logo_file is not None:
                    logo_bytes = logo_file.getvalue()
                
                quick_wins_data = st.session_state.get("quick_wins", [])
                ops_fixes_data = st.session_state.get("ops_fixes", [])
                copy_hooks_ext = st.session_state.get("copy_hooks_extended", None)
                grouped_pos = st.session_state.get("grouped_positive_quotes", None)
                grouped_neg = st.session_state.get("grouped_negative_quotes", None)
                
                pdf_bytes = generate_pdf_report(
                    business_name=business_name,
                    metrics=metrics,
                    themes=analyzer.themes,
                    executive_summary=executive_summary,
                    action_plan=action_plan,
                    copy_hooks=copy_hooks,
                    top_positive_quotes=top_positive_quotes,
                    top_negative_quotes=top_negative_quotes,
                    white_label_mode=white_label_mode,
                    agency_name=agency_name,
                    agency_email=agency_email,
                    agency_phone=agency_phone,
                    client_name=client_name,
                    logo_bytes=logo_bytes,
                    quick_wins=quick_wins_data,
                    ops_fixes=ops_fixes_data,
                    copy_hooks_extended=copy_hooks_ext,
                    grouped_positive_quotes=grouped_pos,
                    grouped_negative_quotes=grouped_neg,
                    risk_exists=metrics.get("risk_exists", False),
                    risk_level=metrics.get("risk_level", "low")
                )
                
                st.download_button(
                    label="📄 Download PDF Report",
                    data=pdf_bytes,
                    file_name=f"{business_name.replace(' ', '_')}_review_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error generating PDF: {e}")
        
        with col2:
            st.markdown("### Scored CSV")
            st.markdown("Download reviews with sentiment scores")
            
            csv_data = analyzed_df.to_csv(index=False)
            st.download_button(
                label="📊 Download Scored CSV",
                data=csv_data,
                file_name=f"{business_name.replace(' ', '_')}_scored_reviews_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col3:
            st.markdown("### Insights JSON")
            st.markdown("Download all metrics and insights")
            
            domain_result_export = st.session_state.get("domain_result", {})
            discovered_themes_export = st.session_state.get("discovered_themes", [])
            domain_recommendations_export = st.session_state.get("domain_recommendations", {})
            
            insights_data = {
                "business_name": business_name,
                "analysis_date": datetime.now().isoformat(),
                "detected_domain": domain_result_export.get("domain", "other"),
                "domain_confidence": domain_result_export.get("confidence", 0),
                "domain_scores": domain_result_export.get("scores", {}),
                "discovered_themes": discovered_themes_export,
                "domain_recommendations": domain_recommendations_export,
                "metrics": metrics,
                "executive_summary": executive_summary,
                "action_plan": action_plan,
                "copy_hooks": copy_hooks,
                "top_positive_quotes": top_positive_quotes,
                "top_negative_quotes": top_negative_quotes
            }
            
            json_data = json.dumps(insights_data, indent=2, default=str)
            st.download_button(
                label="📋 Download Insights JSON",
                data=json_data,
                file_name=f"{business_name.replace(' ', '_')}_insights_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
        
        st.markdown("---")
        
        st.subheader("Deep CSV Export (V1.3)")
        st.markdown("Extract aspects, issues, pain decomposition, and business flags")
        
        deep_export_enabled = st.checkbox("✨ Deep Export with Aspects & Issues", value=False)
        
        if deep_export_enabled:
            try:
                with st.spinner("Generating deep export..."):
                    # Extract aspects for each review
                    def extract_aspects_row(row):
                        text = row.get(text_col, "")
                        sentiment = row.get("sentiment_label", "neutral")
                        aspects, sentiments = extract_aspects_with_sentiment(text, sentiment, max_aspects=3)
                        return "|".join(aspects)
                    
                    def extract_aspect_sentiments_row(row):
                        text = row.get(text_col, "")
                        sentiment = row.get("sentiment_label", "neutral")
                        aspects, sentiments = extract_aspects_with_sentiment(text, sentiment, max_aspects=3)
                        return "|".join([sentiments.get(a, sentiment) for a in aspects])
                    
                    deep_reviews_df = analyzed_df.copy()
                    deep_reviews_df["aspects"] = deep_reviews_df.apply(extract_aspects_row, axis=1)
                    deep_reviews_df["aspect_sentiments"] = deep_reviews_df.apply(extract_aspect_sentiments_row, axis=1)
                    
                    # Cluster issues by theme
                    issues_df, _ = cluster_issues_by_theme(
                        analyzed_df,
                        theme_col="theme",
                        text_col=text_col,
                        sentiment_col="sentiment_label"
                    )
                    
                    if not issues_df.empty:
                        # Add pain decomposition
                        issues_df = decompose_pain_by_issue(
                            issues_df,
                            analyzed_df,
                            theme_col="theme",
                            sentiment_col="sentiment_label"
                        )
                        
                        # Add business flags
                        issues_df = add_flags_to_issues(issues_df)
                        
                        # Prepare reviews export
                        review_cols_to_export = ["review_text", "rating", "sentiment_label", "severity", "theme", "aspects", "aspect_sentiments"]
                        review_export = deep_reviews_df[[c for c in review_cols_to_export if c in deep_reviews_df.columns]]
                        review_export.columns = ["Review Text", "Rating", "Sentiment", "Severity", "Theme", "Aspects", "Aspect Sentiments"]
                        
                        # Download buttons
                        col_deep1, col_deep2 = st.columns(2)
                        
                        with col_deep1:
                            reviews_csv = review_export.to_csv(index=False)
                            st.download_button(
                                label="📥 Deep Export (Reviews with Aspects)",
                                data=reviews_csv,
                                file_name=f"{business_name.replace(' ', '_')}_deep_reviews_{datetime.now().strftime('%Y%m%d')}.csv",
                                mime="text/csv"
                            )
                        
                        with col_deep2:
                            issues_csv = issues_df.to_csv(index=False)
                            st.download_button(
                                label="📥 Deep Export (Issues & Pain)",
                                data=issues_csv,
                                file_name=f"{business_name.replace(' ', '_')}_deep_issues_{datetime.now().strftime('%Y%m%d')}.csv",
                                mime="text/csv"
                            )
                        
                        st.markdown("**Top Issues Summary**")
                        top_issues = issues_df.nlargest(10, "pain_contribution")[["theme", "issue_label", "support_pct", "negative_ratio", "pain_contribution", "flags"]]
                        st.dataframe(top_issues, use_container_width=True)
                    else:
                        st.info("Not enough negative reviews to cluster issues. Need at least 50 negative reviews per theme.")
            except Exception as e:
                st.error(f"Error generating deep export: {e}")
        
        st.markdown("---")
        st.subheader("Scheduled Reports")
        st.markdown("Configure automated report generation and delivery.")
        
        st.info("📧 **Email Delivery Configuration**")
        
        schedule_enabled = st.toggle("Enable Scheduled Reports", value=False)
        
        if schedule_enabled:
            sched_col1, sched_col2 = st.columns(2)
            
            with sched_col1:
                schedule_frequency = st.selectbox(
                    "Report Frequency",
                    ["Daily", "Weekly", "Monthly"]
                )
                
                if schedule_frequency == "Weekly":
                    schedule_day = st.selectbox("Day of Week", 
                        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
                elif schedule_frequency == "Monthly":
                    schedule_day = st.selectbox("Day of Month", list(range(1, 29)))
                else:
                    schedule_day = None
            
            with sched_col2:
                recipient_emails = st.text_area(
                    "Recipient Emails (one per line)",
                    placeholder="client@example.com\nteam@agency.com"
                )
                
                include_pdf = st.checkbox("Include PDF Report", value=True)
                include_csv = st.checkbox("Include Scored CSV", value=False)
            
            if st.button("Save Schedule Configuration"):
                schedule_config = {
                    "enabled": True,
                    "frequency": schedule_frequency,
                    "day": schedule_day,
                    "recipients": [e.strip() for e in recipient_emails.split("\n") if e.strip()],
                    "include_pdf": include_pdf,
                    "include_csv": include_csv,
                    "business_name": business_name,
                    "created_at": datetime.now().isoformat()
                }
                
                os.makedirs("schedules", exist_ok=True)
                schedule_file = f"schedules/{business_name.replace(' ', '_')}_schedule.json"
                with open(schedule_file, "w") as f:
                    json.dump(schedule_config, f, indent=2)
                
                st.success(f"Schedule saved! Reports will be generated {schedule_frequency.lower()}.")
                st.info("Note: To fully enable email delivery, configure an email service (SMTP or API) in your environment.")
                
                st.download_button(
                    label="📥 Download Schedule Config",
                    data=json.dumps(schedule_config, indent=2),
                    file_name=f"{business_name.replace(' ', '_')}_schedule_config.json",
                    mime="application/json"
                )
        
        st.markdown("---")
        st.subheader("Analyzed Data Preview")
        st.dataframe(analyzed_df.head(20), use_container_width=True)

else:
    st.info("👆 Upload a file (CSV, Excel, or JSON) and click 'Analyze Reviews' to get started!")
    
    st.markdown("---")
    st.subheader("Try with Sample Data")
    
    if os.path.exists("templates/sample_reviews.csv"):
        sample_df = pd.read_csv("templates/sample_reviews.csv")
        st.markdown(f"We have a sample file with {len(sample_df)} demo reviews. Download it to test the app:")
        
        sample_csv = sample_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Sample CSV",
            data=sample_csv,
            file_name="sample_gold_coast_reviews.csv",
            mime="text/csv"
        )

st.sidebar.markdown("---")
st.sidebar.caption("Review Intelligence v1.2")
st.sidebar.caption("For marketing agencies")
