"""
Gold Coast Review Collector
A tool to collect and normalize customer reviews into a standardized CSV format.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

from src.parsers import parse_pasted_reviews, create_reviews_dataframe
from src.mapping import transform_uploaded_df
from src.cleaning import clean_dataframe
from src.quality import generate_quality_report, report_to_json
from src.sentiment import add_sentiment_to_df, get_sentiment_summary
from src.exports import export_to_csv, export_to_json, export_to_excel, read_excel_file, read_csv_file
from src.gbp_client import (
    get_auth_url, exchange_code_for_tokens, get_credentials, clear_credentials,
    is_connected, list_accounts, list_locations, list_reviews, get_secrets_status
)
from src.gbp_normalize import normalize_reviews_to_df, get_location_display_name, get_account_display_name

st.set_page_config(
    page_title="Gold Coast Review Collector",
    page_icon="⭐",
    layout="wide"
)

st.title("Gold Coast Review Collector")
st.markdown("*This tool converts pasted reviews or exported files into a standardized CSV for the Review Intelligence report.*")

if 'standardized_df' not in st.session_state:
    st.session_state.standardized_df = None
if 'quality_report' not in st.session_state:
    st.session_state.quality_report = None
if 'paste_stats' not in st.session_state:
    st.session_state.paste_stats = None
if 'merged_sources' not in st.session_state:
    st.session_state.merged_sources = []
if 'merged_df' not in st.session_state:
    st.session_state.merged_df = None
if 'gbp_accounts' not in st.session_state:
    st.session_state.gbp_accounts = []
if 'gbp_locations' not in st.session_state:
    st.session_state.gbp_locations = []
if 'gbp_reviews_df' not in st.session_state:
    st.session_state.gbp_reviews_df = None
if 'gbp_oauth_completed' not in st.session_state:
    st.session_state.gbp_oauth_completed = False

query_params = st.query_params
if 'code' in query_params and not st.session_state.gbp_oauth_completed:
    code = query_params.get('code')
    if code:
        success = exchange_code_for_tokens(code)
        if success:
            st.session_state.gbp_oauth_completed = True
            st.query_params.clear()
            st.rerun()

def get_timestamp():
    return datetime.now().strftime('%Y%m%d')

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Paste Reviews", 
    "Upload & Map Files", 
    "Batch Upload",
    "Merge Sources",
    "Google (GBP API)",
    "Help / Templates"
])

with tab1:
    st.header("Paste Reviews")
    st.markdown("""
    Paste your reviews below. Supported formats:
    - **One review per line**
    - **Reviews separated by `---`** on its own line
    """)
    
    raw_text = st.text_area(
        "Paste reviews here",
        height=250,
        placeholder="Paste your reviews here...\nOne per line, or separate with ---"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        source = st.selectbox(
            "Source",
            options=["Google", "Facebook", "Tripadvisor", "Yelp", "Other"],
            index=0
        )
    
    with col2:
        default_rating = st.selectbox(
            "Default rating (optional)",
            options=["", "5", "4", "3", "2", "1"],
            index=0
        )
    
    use_default_date = st.checkbox("Set default date", value=False)
    if use_default_date:
        default_date = st.date_input(
            "Default date",
            value="today"
        )
        default_date_str = default_date.strftime('%Y-%m-%d')
    else:
        default_date_str = ''
    
    col3, col4, col5 = st.columns(3)
    with col3:
        remove_duplicates = st.checkbox("Remove duplicates", value=True)
    with col4:
        remove_short = st.checkbox("Remove short reviews (< 10 chars)", value=True)
    with col5:
        add_sentiment = st.checkbox("Add sentiment analysis", value=False)
    
    if st.button("Parse Reviews", type="primary", use_container_width=True, key="parse_btn"):
        if raw_text.strip():
            reviews = parse_pasted_reviews(raw_text)
            records = create_reviews_dataframe(
                reviews,
                source=source,
                default_rating=default_rating,
                default_date=default_date_str
            )
            
            if records:
                df = pd.DataFrame(records)
                rows_before_clean = len(df)
                
                df, clean_stats = clean_dataframe(
                    df,
                    text_column='review_text',
                    remove_duplicates=remove_duplicates,
                    remove_short_reviews=remove_short,
                    trim_whitespace=True
                )
                
                if add_sentiment:
                    df = add_sentiment_to_df(df, 'review_text')
                
                st.session_state.standardized_df = df
                st.session_state.paste_stats = {
                    'total_parsed': rows_before_clean,
                    'duplicates_removed': clean_stats['duplicates_removed'],
                    'short_removed': clean_stats['short_removed'],
                    'final_rows': len(df)
                }
                
                sentiment_data = get_sentiment_summary(df) if add_sentiment else None
                
                st.session_state.quality_report = generate_quality_report(
                    rows_in=rows_before_clean,
                    rows_out=len(df),
                    duplicates_removed=clean_stats['duplicates_removed'],
                    short_removed=clean_stats['short_removed'],
                    sentiment_summary=sentiment_data
                )
                
                st.success(f"Parsed {len(df)} reviews successfully!")
            else:
                st.warning("No reviews found in the pasted text.")
        else:
            st.warning("Please paste some reviews first.")
    
    if st.session_state.standardized_df is not None and st.session_state.paste_stats is not None:
        stats = st.session_state.paste_stats
        st.markdown("---")
        st.subheader("Parsing Results")
        
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("Total Parsed", stats['total_parsed'])
        col_s2.metric("Duplicates Removed", stats['duplicates_removed'])
        col_s3.metric("Short Removed", stats['short_removed'])
        col_s4.metric("Final Rows", stats['final_rows'])
        
        st.dataframe(st.session_state.standardized_df, use_container_width=True)
        
        st.subheader("Download Options")
        col_d1, col_d2, col_d3 = st.columns(3)
        
        with col_d1:
            csv_data = export_to_csv(st.session_state.standardized_df)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"reviews_standardized_{get_timestamp()}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_d2:
            json_data = export_to_json(st.session_state.standardized_df)
            st.download_button(
                label="Download JSON",
                data=json_data,
                file_name=f"reviews_standardized_{get_timestamp()}.json",
                mime="application/json",
                use_container_width=True
            )
        
        with col_d3:
            excel_data = export_to_excel(st.session_state.standardized_df)
            st.download_button(
                label="Download Excel",
                data=excel_data,
                file_name=f"reviews_standardized_{get_timestamp()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

with tab2:
    st.header("Upload & Map Files")
    st.markdown("Upload a CSV or Excel file and map its columns to the standard format.")
    
    uploaded_file = st.file_uploader("Choose a CSV or Excel file", type=['csv', 'xlsx', 'xls'], key="single_upload")
    
    if uploaded_file is not None:
        try:
            file_content = uploaded_file.read()
            file_name = uploaded_file.name.lower()
            
            if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                uploaded_df = read_excel_file(file_content)
            else:
                uploaded_df = read_csv_file(file_content)
            
            st.subheader("Detected Columns")
            st.write(f"Found {len(uploaded_df)} rows and {len(uploaded_df.columns)} columns")
            st.dataframe(uploaded_df.head(5), use_container_width=True)
            
            columns = [''] + list(uploaded_df.columns)
            
            st.subheader("Column Mapping")
            
            col1, col2 = st.columns(2)
            
            with col1:
                text_col = st.selectbox(
                    "Review text column (required)",
                    options=columns[1:],
                    index=0
                )
                
                rating_col = st.selectbox(
                    "Rating column (optional)",
                    options=columns,
                    index=0
                )
            
            with col2:
                date_col = st.selectbox(
                    "Date column (optional)",
                    options=columns,
                    index=0
                )
                
                source_col = st.selectbox(
                    "Source column (optional)",
                    options=columns,
                    index=0
                )
            
            if not source_col:
                default_source = st.selectbox(
                    "Default source (if no source column)",
                    options=["Google", "Facebook", "Tripadvisor", "Yelp", "Other", ""],
                    index=0
                )
            else:
                default_source = None
            
            if date_col:
                date_format = st.selectbox(
                    "Date format hint",
                    options=["Auto-detect", "ISO (YYYY-MM-DD)", "D/M/YYYY", "M/D/YYYY"],
                    index=0
                )
                date_format_hint = {
                    "Auto-detect": None,
                    "ISO (YYYY-MM-DD)": "ISO",
                    "D/M/YYYY": "DMY",
                    "M/D/YYYY": "MDY"
                }.get(date_format)
            else:
                date_format_hint = None
            
            st.subheader("Options")
            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            with col_c1:
                csv_remove_duplicates = st.checkbox("Remove duplicates", value=True, key="csv_dedup")
            with col_c2:
                csv_trim_whitespace = st.checkbox("Trim whitespace", value=True, key="csv_trim")
            with col_c3:
                csv_remove_short = st.checkbox("Remove short reviews", value=True, key="csv_short")
            with col_c4:
                csv_add_sentiment = st.checkbox("Add sentiment", value=False, key="csv_sentiment")
            
            if st.button("Transform to Standard Format", type="primary", use_container_width=True):
                transformed_df, transform_stats = transform_uploaded_df(
                    uploaded_df,
                    text_col=text_col,
                    rating_col=rating_col if rating_col else None,
                    date_col=date_col if date_col else None,
                    source_col=source_col if source_col else None,
                    default_source=default_source,
                    date_format_hint=date_format_hint
                )
                
                transformed_df, clean_stats = clean_dataframe(
                    transformed_df,
                    text_column='review_text',
                    remove_duplicates=csv_remove_duplicates,
                    remove_short_reviews=csv_remove_short,
                    trim_whitespace=csv_trim_whitespace
                )
                
                if csv_add_sentiment:
                    transformed_df = add_sentiment_to_df(transformed_df, 'review_text')
                
                st.session_state.standardized_df = transformed_df
                
                sentiment_data = get_sentiment_summary(transformed_df) if csv_add_sentiment else None
                
                st.session_state.quality_report = generate_quality_report(
                    rows_in=transform_stats['rows_in'],
                    rows_out=len(transformed_df),
                    duplicates_removed=clean_stats['duplicates_removed'],
                    short_removed=clean_stats['short_removed'],
                    missing_text_count=transform_stats['missing_text_count'],
                    rating_invalid_count=transform_stats['rating_invalid_count'],
                    date_parse_fail_count=transform_stats['date_parse_fail_count'],
                    additional_warnings=transform_stats.get('warnings', []),
                    sentiment_summary=sentiment_data
                )
                
                st.success(f"Transformed {len(transformed_df)} reviews!")
            
            if st.session_state.standardized_df is not None and st.session_state.quality_report is not None:
                st.markdown("---")
                st.subheader("Standardized Output")
                st.dataframe(st.session_state.standardized_df, use_container_width=True)
                
                st.subheader("Data Quality Report")
                report = st.session_state.quality_report
                
                col_q1, col_q2, col_q3 = st.columns(3)
                col_q1.metric("Input Rows", report['rows_in'])
                col_q2.metric("Output Rows", report['rows_out'])
                col_q3.metric("Rows Removed", report['rows_in'] - report['rows_out'])
                
                if report.get('sentiment_summary'):
                    st.subheader("Sentiment Analysis")
                    sent = report['sentiment_summary']
                    col_sent1, col_sent2, col_sent3 = st.columns(3)
                    col_sent1.metric("Positive", sent['positive_count'])
                    col_sent2.metric("Neutral", sent['neutral_count'])
                    col_sent3.metric("Negative", sent['negative_count'])
                
                if report['warnings']:
                    st.warning("Warnings:")
                    for warning in report['warnings']:
                        st.write(f"- {warning}")
                
                st.subheader("Download Options")
                col_d1, col_d2, col_d3, col_d4 = st.columns(4)
                
                with col_d1:
                    csv_data = export_to_csv(st.session_state.standardized_df)
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"reviews_standardized_{get_timestamp()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                with col_d2:
                    json_data = export_to_json(st.session_state.standardized_df)
                    st.download_button(
                        label="Download JSON",
                        data=json_data,
                        file_name=f"reviews_standardized_{get_timestamp()}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                
                with col_d3:
                    excel_data = export_to_excel(st.session_state.standardized_df)
                    st.download_button(
                        label="Download Excel",
                        data=excel_data,
                        file_name=f"reviews_standardized_{get_timestamp()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                with col_d4:
                    quality_json = report_to_json(st.session_state.quality_report)
                    st.download_button(
                        label="Quality Report",
                        data=quality_json,
                        file_name=f"reviews_quality_{get_timestamp()}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                    
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")

with tab3:
    st.header("Batch Upload")
    st.markdown("Upload multiple CSV or Excel files at once for batch processing.")
    
    batch_files = st.file_uploader(
        "Choose multiple files",
        type=['csv', 'xlsx', 'xls'],
        accept_multiple_files=True,
        key="batch_upload"
    )
    
    if batch_files:
        st.write(f"Uploaded {len(batch_files)} files")
        
        col1, col2 = st.columns(2)
        with col1:
            batch_text_col = st.text_input("Review text column name", value="Review", help="Column name for review text (case-sensitive)")
            batch_rating_col = st.text_input("Rating column name (optional)", value="", help="Leave empty to skip")
        with col2:
            batch_date_col = st.text_input("Date column name (optional)", value="", help="Leave empty to skip")
            batch_source_col = st.text_input("Source column name (optional)", value="", help="Leave empty to use filename")
        
        col3, col4, col5 = st.columns(3)
        with col3:
            batch_dedup = st.checkbox("Remove duplicates", value=True, key="batch_dedup")
        with col4:
            batch_short = st.checkbox("Remove short reviews", value=True, key="batch_short")
        with col5:
            batch_sentiment = st.checkbox("Add sentiment", value=False, key="batch_sentiment")
        
        if st.button("Process All Files", type="primary", use_container_width=True):
            all_dfs = []
            total_rows = 0
            processed_files = []
            errors = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, file in enumerate(batch_files):
                try:
                    status_text.text(f"Processing {file.name}...")
                    file_content = file.read()
                    file_name = file.name.lower()
                    
                    if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                        df = read_excel_file(file_content)
                    else:
                        df = read_csv_file(file_content)
                    
                    if batch_text_col not in df.columns:
                        possible_cols = [c for c in df.columns if 'review' in c.lower() or 'text' in c.lower() or 'comment' in c.lower()]
                        if possible_cols:
                            text_col = possible_cols[0]
                        else:
                            text_col = df.columns[0]
                    else:
                        text_col = batch_text_col
                    
                    source_name = file.name.rsplit('.', 1)[0] if not batch_source_col else None
                    
                    transformed_df, _ = transform_uploaded_df(
                        df,
                        text_col=text_col,
                        rating_col=batch_rating_col if batch_rating_col and batch_rating_col in df.columns else None,
                        date_col=batch_date_col if batch_date_col and batch_date_col in df.columns else None,
                        source_col=batch_source_col if batch_source_col and batch_source_col in df.columns else None,
                        default_source=source_name
                    )
                    
                    transformed_df['_source_file'] = file.name
                    all_dfs.append(transformed_df)
                    total_rows += len(transformed_df)
                    processed_files.append(file.name)
                    
                except Exception as e:
                    errors.append(f"{file.name}: {str(e)}")
                
                progress_bar.progress((i + 1) / len(batch_files))
            
            if all_dfs:
                combined_df = pd.concat(all_dfs, ignore_index=True)
                
                combined_df, clean_stats = clean_dataframe(
                    combined_df,
                    text_column='review_text',
                    remove_duplicates=batch_dedup,
                    remove_short_reviews=batch_short,
                    trim_whitespace=True
                )
                
                if batch_sentiment:
                    combined_df = add_sentiment_to_df(combined_df, 'review_text')
                
                final_df = combined_df.drop(columns=['_source_file'], errors='ignore')
                st.session_state.standardized_df = final_df
                
                sentiment_data = get_sentiment_summary(final_df) if batch_sentiment else None
                
                st.session_state.quality_report = generate_quality_report(
                    rows_in=total_rows,
                    rows_out=len(final_df),
                    duplicates_removed=clean_stats['duplicates_removed'],
                    short_removed=clean_stats['short_removed'],
                    sentiment_summary=sentiment_data
                )
                
                status_text.empty()
                st.success(f"Processed {len(processed_files)} files with {len(final_df)} total reviews!")
                
                if errors:
                    st.warning(f"Errors in {len(errors)} files:")
                    for err in errors:
                        st.write(f"- {err}")
                
                st.subheader("Combined Results")
                st.dataframe(final_df, use_container_width=True)
                
                st.subheader("Download Options")
                col_d1, col_d2, col_d3 = st.columns(3)
                
                with col_d1:
                    csv_data = export_to_csv(final_df)
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"reviews_batch_{get_timestamp()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="batch_csv"
                    )
                
                with col_d2:
                    json_data = export_to_json(final_df)
                    st.download_button(
                        label="Download JSON",
                        data=json_data,
                        file_name=f"reviews_batch_{get_timestamp()}.json",
                        mime="application/json",
                        use_container_width=True,
                        key="batch_json"
                    )
                
                with col_d3:
                    excel_data = export_to_excel(final_df)
                    st.download_button(
                        label="Download Excel",
                        data=excel_data,
                        file_name=f"reviews_batch_{get_timestamp()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="batch_excel"
                    )
            else:
                st.error("No files could be processed successfully.")

with tab4:
    st.header("Merge Sources")
    st.markdown("Combine reviews from multiple sources into a single standardized dataset.")
    
    st.subheader("Add Source Data")
    
    source_name = st.text_input("Source name (e.g., Google, Facebook)", key="merge_source_name")
    source_file = st.file_uploader("Upload file", type=['csv', 'xlsx', 'xls'], key="merge_file")
    
    if source_file and source_name:
        try:
            file_content = source_file.read()
            file_name = source_file.name.lower()
            
            if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                preview_df = read_excel_file(file_content)
            else:
                preview_df = read_csv_file(file_content)
            
            st.write(f"Preview ({len(preview_df)} rows):")
            st.dataframe(preview_df.head(3), use_container_width=True)
            
            merge_text_col = st.selectbox(
                "Review text column",
                options=list(preview_df.columns),
                key="merge_text_col"
            )
            
            if st.button("Add to Merge List", type="primary"):
                transformed_df, _ = transform_uploaded_df(
                    preview_df,
                    text_col=merge_text_col,
                    default_source=source_name
                )
                
                st.session_state.merged_sources.append({
                    'name': source_name,
                    'count': len(transformed_df),
                    'data': transformed_df
                })
                st.success(f"Added {len(transformed_df)} reviews from {source_name}")
                st.rerun()
                
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
    
    if st.session_state.merged_sources:
        st.markdown("---")
        st.subheader("Sources to Merge")
        
        for i, src in enumerate(st.session_state.merged_sources):
            col1, col2 = st.columns([3, 1])
            col1.write(f"**{src['name']}**: {src['count']} reviews")
            if col2.button("Remove", key=f"remove_{i}"):
                st.session_state.merged_sources.pop(i)
                st.rerun()
        
        total_reviews = sum(s['count'] for s in st.session_state.merged_sources)
        st.info(f"Total: {total_reviews} reviews from {len(st.session_state.merged_sources)} sources")
        
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            merge_dedup = st.checkbox("Remove duplicates", value=True, key="merge_dedup")
        with col_opt2:
            merge_short = st.checkbox("Remove short reviews", value=True, key="merge_short")
        with col_opt3:
            merge_sentiment = st.checkbox("Add sentiment", value=False, key="merge_sentiment")
        
        if st.button("Merge All Sources", type="primary", use_container_width=True):
            all_dfs = [s['data'] for s in st.session_state.merged_sources]
            merged_df = pd.concat(all_dfs, ignore_index=True)
            
            merged_df, clean_stats = clean_dataframe(
                merged_df,
                text_column='review_text',
                remove_duplicates=merge_dedup,
                remove_short_reviews=merge_short,
                trim_whitespace=True
            )
            
            if merge_sentiment:
                merged_df = add_sentiment_to_df(merged_df, 'review_text')
            
            st.session_state.merged_df = merged_df
            st.session_state.standardized_df = merged_df
            
            sentiment_data = get_sentiment_summary(merged_df) if merge_sentiment else None
            
            st.session_state.quality_report = generate_quality_report(
                rows_in=total_reviews,
                rows_out=len(merged_df),
                duplicates_removed=clean_stats['duplicates_removed'],
                short_removed=clean_stats['short_removed'],
                sentiment_summary=sentiment_data
            )
            
            st.success(f"Merged {len(merged_df)} reviews!")
        
        if st.session_state.merged_df is not None:
            st.markdown("---")
            st.subheader("Merged Results")
            st.dataframe(st.session_state.merged_df, use_container_width=True)
            
            if st.session_state.quality_report:
                st.subheader("Data Quality Report")
                report = st.session_state.quality_report
                
                col_q1, col_q2, col_q3 = st.columns(3)
                col_q1.metric("Input Rows", report['rows_in'])
                col_q2.metric("Output Rows", report['rows_out'])
                col_q3.metric("Rows Removed", report['rows_in'] - report['rows_out'])
                
                if report.get('sentiment_summary'):
                    st.subheader("Sentiment Analysis")
                    sent = report['sentiment_summary']
                    col_sent1, col_sent2, col_sent3 = st.columns(3)
                    col_sent1.metric("Positive", sent['positive_count'])
                    col_sent2.metric("Neutral", sent['neutral_count'])
                    col_sent3.metric("Negative", sent['negative_count'])
            
            source_counts = st.session_state.merged_df['source'].value_counts()
            st.subheader("Reviews by Source")
            st.bar_chart(source_counts)
            
            st.subheader("Download Options")
            col_d1, col_d2, col_d3, col_d4 = st.columns(4)
            
            with col_d1:
                csv_data = export_to_csv(st.session_state.merged_df)
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name=f"reviews_merged_{get_timestamp()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="merged_csv"
                )
            
            with col_d2:
                json_data = export_to_json(st.session_state.merged_df)
                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name=f"reviews_merged_{get_timestamp()}.json",
                    mime="application/json",
                    use_container_width=True,
                    key="merged_json"
                )
            
            with col_d3:
                excel_data = export_to_excel(st.session_state.merged_df)
                st.download_button(
                    label="Download Excel",
                    data=excel_data,
                    file_name=f"reviews_merged_{get_timestamp()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="merged_excel"
                )
            
            with col_d4:
                if st.session_state.quality_report:
                    quality_json = report_to_json(st.session_state.quality_report)
                    st.download_button(
                        label="Quality Report",
                        data=quality_json,
                        file_name=f"reviews_quality_{get_timestamp()}.json",
                        mime="application/json",
                        use_container_width=True,
                        key="merged_quality"
                    )
        
        if st.button("Clear All Sources"):
            st.session_state.merged_sources = []
            st.session_state.merged_df = None
            st.rerun()

with tab5:
    st.header("Google (GBP API Pull)")
    st.markdown("Pull reviews directly from your Google Business Profile using the official API.")
    
    if st.session_state.gbp_oauth_completed:
        st.success("Successfully connected to Google!")
        st.session_state.gbp_oauth_completed = False
    
    secrets_status = get_secrets_status()
    
    with st.expander("🔧 Diagnostics"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**CLIENT_ID**: {secrets_status['client_id']}")
        with col2:
            st.write(f"**CLIENT_SECRET**: {secrets_status['client_secret']}")
        with col3:
            st.write(f"**REDIRECT_URI**: {secrets_status['redirect_uri']}")
        
        try:
            import streamlit.web.bootstrap as bootstrap
            base_url = bootstrap._get_session().client_state.query_string if hasattr(bootstrap, '_get_session') else ''
        except:
            base_url = ''
        
        if base_url or "replit.dev" in str(base_url):
            st.warning("⚠️ Running under embedded preview may break OAuth redirect. Use published app URL in Redirect URI.")
        
        st.markdown("**Redirect URI being used:**")
        st.code(secrets_status['redirect_uri_value'], language="plaintext")
    
    if not secrets_status['all_configured']:
        missing = []
        if not secrets_status['client_id']: missing.append("GOOGLE_OAUTH_CLIENT_ID")
        if not secrets_status['client_secret']: missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
        if not secrets_status['redirect_uri']: missing.append("GOOGLE_OAUTH_REDIRECT_URI")
        
        st.warning("Missing secrets configuration")
        st.markdown("**Set these Replit secrets:**")
        for key in missing:
            st.write(f"☐ {key}")
        
        st.subheader("Setup Instructions")
        st.markdown("""
        To use the Google Business Profile API, you need to:
        
        1. **Create a Google Cloud Project** at [console.cloud.google.com](https://console.cloud.google.com)
        
        2. **Enable APIs**:
           - My Business Account Management API
           - My Business Business Information API
           - My Business API (for reviews)
        
        3. **Configure OAuth Consent Screen**:
           - Set User Type to "External"
           - Add your email as a test user
           - Add scope: `https://www.googleapis.com/auth/business.manage`
        
        4. **Create OAuth 2.0 Client ID**:
           - Application type: Web application
           - Add Authorized redirect URI (see Diagnostics above)
        
        5. **Set Replit Secrets** (see checklist above)
        
        After setting up, refresh this page.
        """)
        
    else:
        connected = is_connected()
        
        st.subheader("Connection Status")
        if connected:
            st.success("Connected to Google")
        else:
            st.warning("Not connected")
            st.markdown(f"**Redirect URI for Google Cloud Console:**")
            st.code(secrets_status['redirect_uri_value'])
            
            auth_url = get_auth_url()
            if auth_url:
                st.markdown(f"[Click here to Connect to Google]({auth_url})")
            else:
                st.error("Could not generate authorization URL.")
        
        if connected:
            creds = get_credentials()
            
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("Disconnect", type="secondary"):
                    clear_credentials()
                    st.session_state.gbp_accounts = []
                    st.session_state.gbp_locations = []
                    st.session_state.gbp_reviews_df = None
                    st.rerun()
            
            st.subheader("Select Account & Location")
            
            if st.button("Load Accounts", key="load_accounts"):
                with st.spinner("Loading accounts..."):
                    accounts, error = list_accounts(creds)
                    if error:
                        st.error(f"Error loading accounts: {error}")
                    else:
                        st.session_state.gbp_accounts = accounts
                        if accounts:
                            st.success(f"Found {len(accounts)} account(s)")
                        else:
                            st.warning("No accounts found. Make sure you have access to a Google Business Profile.")
            
            if st.session_state.gbp_accounts:
                account_options = {get_account_display_name(a): a['name'] for a in st.session_state.gbp_accounts}
                selected_account_name = st.selectbox(
                    "Select Account",
                    options=list(account_options.keys()),
                    key="gbp_account_select"
                )
                
                if selected_account_name:
                    account_resource = account_options[selected_account_name]
                    
                    if st.button("Load Locations", key="load_locations"):
                        with st.spinner("Loading locations..."):
                            locations, error = list_locations(creds, account_resource)
                            if error:
                                st.error(f"Error loading locations: {error}")
                            else:
                                st.session_state.gbp_locations = locations
                                if locations:
                                    st.success(f"Found {len(locations)} location(s)")
                                else:
                                    st.warning("No locations found for this account.")
            
            if st.session_state.gbp_locations:
                location_options = {get_location_display_name(l): l['name'] for l in st.session_state.gbp_locations}
                selected_location_name = st.selectbox(
                    "Select Location",
                    options=list(location_options.keys()),
                    key="gbp_location_select"
                )
                
                st.subheader("Pull Options")
                
                max_reviews = st.number_input(
                    "Maximum reviews to fetch",
                    min_value=50,
                    max_value=2000,
                    value=200,
                    step=50
                )
                
                col_opt1, col_opt2, col_opt3 = st.columns(3)
                with col_opt1:
                    gbp_dedup = st.checkbox("Remove duplicates", value=True, key="gbp_dedup")
                with col_opt2:
                    gbp_short = st.checkbox("Remove short reviews", value=True, key="gbp_short")
                with col_opt3:
                    gbp_trim = st.checkbox("Trim whitespace", value=True, key="gbp_trim")
                
                if st.button("Pull Reviews", type="primary", use_container_width=True):
                    if selected_location_name:
                        location_resource = location_options[selected_location_name]
                        
                        with st.spinner(f"Fetching up to {max_reviews} reviews..."):
                            reviews, error = list_reviews(creds, location_resource, max_reviews)
                            
                            if error:
                                st.error(f"Error fetching reviews: {error}")
                            elif not reviews:
                                st.warning("No reviews found for this location.")
                            else:
                                df = normalize_reviews_to_df(reviews)
                                rows_before = len(df)
                                
                                df, clean_stats = clean_dataframe(
                                    df,
                                    text_column='review_text',
                                    remove_duplicates=gbp_dedup,
                                    remove_short_reviews=gbp_short,
                                    trim_whitespace=gbp_trim
                                )
                                
                                st.session_state.gbp_reviews_df = df
                                st.session_state.standardized_df = df
                                
                                st.session_state.quality_report = generate_quality_report(
                                    rows_in=rows_before,
                                    rows_out=len(df),
                                    duplicates_removed=clean_stats['duplicates_removed'],
                                    short_removed=clean_stats['short_removed']
                                )
                                
                                st.success(f"Fetched and processed {len(df)} reviews!")
                    else:
                        st.warning("Please select a location first.")
            
            if st.session_state.gbp_reviews_df is not None and not st.session_state.gbp_reviews_df.empty:
                st.markdown("---")
                st.subheader("Fetched Reviews")
                st.dataframe(st.session_state.gbp_reviews_df, use_container_width=True)
                
                if st.session_state.quality_report:
                    report = st.session_state.quality_report
                    col_q1, col_q2, col_q3 = st.columns(3)
                    col_q1.metric("Total Fetched", report['rows_in'])
                    col_q2.metric("After Cleaning", report['rows_out'])
                    col_q3.metric("Removed", report['rows_in'] - report['rows_out'])
                
                st.subheader("Download")
                col_d1, col_d2 = st.columns(2)
                
                location_slug = selected_location_name.replace(' ', '_').replace('-', '_')[:20] if 'selected_location_name' in dir() else 'location'
                
                with col_d1:
                    csv_data = export_to_csv(st.session_state.gbp_reviews_df)
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"reviews_google_{location_slug}_{get_timestamp()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="gbp_csv"
                    )
                
                with col_d2:
                    if st.session_state.quality_report:
                        quality_json = report_to_json(st.session_state.quality_report)
                        st.download_button(
                            label="Download Quality JSON",
                            data=quality_json,
                            file_name=f"reviews_google_quality_{get_timestamp()}.json",
                            mime="application/json",
                            use_container_width=True,
                            key="gbp_quality"
                        )

with tab6:
    st.header("Help & Templates")
    
    st.subheader("How to Use This Tool")
    
    st.markdown("""
    ### Getting Reviews Ethically
    
    This tool helps you organize reviews you've collected manually. Here are ethical ways to gather reviews:
    
    1. **Copy from your own platforms**: If you manage a business, copy reviews from your Google Business Profile, Facebook Page, or Tripadvisor listing.
    
    2. **Ask customers directly**: Request written feedback via email or feedback forms.
    
    3. **Export from review platforms**: Some platforms allow business owners to export their reviews.
    
    **Important**: Do NOT use web scraping or automated tools to collect reviews from websites.
    
    ---
    
    ### Supported File Formats
    
    - **CSV** (.csv) - Comma-separated values
    - **Excel** (.xlsx, .xls) - Microsoft Excel format
    
    ---
    
    ### Output Format
    
    The standardized output has these columns:
    
    | Column | Description |
    |--------|-------------|
    | `date` | Review date in YYYY-MM-DD format (optional) |
    | `rating` | Numeric rating 1-5 (optional) |
    | `review_text` | The actual review content (required) |
    | `source` | Platform name like Google, Facebook (optional) |
    
    With sentiment analysis enabled, these additional columns are added:
    
    | Column | Description |
    |--------|-------------|
    | `sentiment_polarity` | Score from -1 (negative) to 1 (positive) |
    | `sentiment_subjectivity` | Score from 0 (objective) to 1 (subjective) |
    | `sentiment_label` | positive, neutral, or negative |
    
    ---
    
    ### Export Formats
    
    You can download your processed reviews in three formats:
    - **CSV** - For spreadsheet applications and data analysis
    - **JSON** - For web applications and APIs
    - **Excel** - For Microsoft Excel with formatting
    
    ---
    
    ### Features
    
    - **Paste Reviews**: Quick entry of text reviews
    - **Upload & Map**: Process single files with column mapping
    - **Batch Upload**: Process multiple files at once
    - **Merge Sources**: Combine reviews from different platforms
    - **Sentiment Analysis**: Automatic positive/negative classification
    """)
    
    st.subheader("Download Templates")
    
    col1, col2 = st.columns(2)
    
    with col1:
        try:
            with open('templates/sample_raw_text.txt', 'r') as f:
                sample_text = f.read()
            st.download_button(
                label="Download Sample Raw Text",
                data=sample_text,
                file_name="sample_raw_text.txt",
                mime="text/plain",
                use_container_width=True
            )
            st.caption("Example of pasted review format with --- separators")
        except FileNotFoundError:
            st.warning("Sample text file not found")
    
    with col2:
        try:
            with open('templates/sample_export.csv', 'r') as f:
                sample_csv = f.read()
            st.download_button(
                label="Download Sample CSV",
                data=sample_csv,
                file_name="sample_export.csv",
                mime="text/csv",
                use_container_width=True
            )
            st.caption("Example CSV showing column mapping")
        except FileNotFoundError:
            st.warning("Sample CSV file not found")
    
    st.subheader("Template Previews")
    
    with st.expander("Preview: Sample Raw Text"):
        try:
            with open('templates/sample_raw_text.txt', 'r') as f:
                st.text(f.read())
        except FileNotFoundError:
            st.warning("File not found")
    
    with st.expander("Preview: Sample CSV"):
        try:
            sample_df = pd.read_csv('templates/sample_export.csv')
            st.dataframe(sample_df, use_container_width=True)
        except FileNotFoundError:
            st.warning("File not found")
