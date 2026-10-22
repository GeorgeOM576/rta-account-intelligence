"""Presentation-only Red Thread branding. No application state or business operations."""
from pathlib import Path
from html import escape
from base64 import b64encode
import streamlit as st
from collections import Counter


def bulk_review_notice(project):
    """Session-only, bounded rendering of the latest bulk operation's results."""
    notice_key = f'bulk_notice_{project}'
    notice = st.session_state.get(notice_key)
    if notice is None:
        return
    report = notice.get('report', notice)  # Also accept a notice from an older live session.
    saved, warnings = len(report['saved']), report['skipped']
    message = (f"Bulk review: Selected {saved + len(warnings)} · Saved {saved} · "
               f"Skipped {len(warnings)} · Warnings {len(warnings)}. ")
    if saved:
        message += f'Review decisions saved for {saved} accounts. Results and exports are up to date.'
    else:
        message += 'No decisions saved.'
    (st.warning if warnings else st.success)(message)
    if warnings:
        scope = f"{project}_{notice.get('operation', 0)}"
        with st.expander('View Warnings'):
            reasons = Counter(item['reason'] for item in warnings)
            st.dataframe([{'Reason': reason, 'Accounts': count} for reason, count in reasons.items()],
                         hide_index=True, height=180, width='stretch')
            reason = st.selectbox('Warning reason', ['All reasons', *reasons], key=f'warning_reason_{scope}')
            affected = warnings if reason == 'All reasons' else [w for w in warnings if w['reason'] == reason]
            pages = max(1, (len(affected) + 49) // 50)
            page = st.number_input('Warning page', min_value=1, max_value=pages, step=1,
                                   key=f'warning_page_{scope}_{reason}')
            start = (page - 1) * 50
            st.caption(f'Warnings {start + 1}–{min(start + 50, len(affected))} of {len(affected)}')
            st.dataframe([{'Row': w['row_id'] + 1, 'Account identifier': w['identifier'], 'Reason': w['reason']}
                          for w in affected[start:start + 50]], hide_index=True, height=320, width='stretch')
    if st.button('Clear All Warnings', key=f'clear_bulk_notice_{project}'):
        del st.session_state[notice_key]
        st.rerun()

LOGO_PATH = Path('assets/redthreadadvising_logo.jpg')


def apply_brand():
    page_options = {'page_title': 'RTA Account Intelligence | Red Thread', 'layout': 'wide'}
    if LOGO_PATH.is_file():
        page_options['page_icon'] = str(LOGO_PATH)
    st.set_page_config(**page_options)
    # Scope custom styling to explicit, stable container keys, not generated DOM names.
    st.markdown('''<style>
    .st-key-redthread_header {
        background: #FFFFFF; border: 1px solid #DDE1E7;
        border-top: 4px solid #D71920; border-radius: 12px;
        padding: 12px 16px; margin-bottom: 12px;
    }
    .st-key-redthread_header h1 {letter-spacing: -0.035em; line-height: 1.15;}
    .redthread-brand {display: flex; align-items: center; gap: 10px; min-width: 0;}
    .redthread-brand img {width: 48px; height: 48px; object-fit: contain; flex: 0 0 48px; display: block;}
    .redthread-brand h1 {margin: 0; padding: 0; font-size: clamp(1.5rem, 3vw, 2.5rem);}
    .redthread-brand-sidebar {gap: 8px;}
    .redthread-brand-sidebar img {width: 40px; height: 40px; flex-basis: 40px;}
    .redthread-brand-sidebar strong {font-size: 1rem; line-height: 1.3; color: #FFFFFF;}
    .st-key-redthread_navigation label {
        padding: 8px 12px; border-left: 3px solid transparent; border-radius: 6px;
    }
    .st-key-redthread_navigation label:has(input:checked) {
        background: #281C2B; border-left-color: #D71920; font-weight: 600;
    }
    .st-key-redthread_navigation label:hover {background: #142238;}
    .st-key-redthread_navigation label:focus-within {outline: 2px solid #FFFFFF; outline-offset: 2px;}
    .st-key-redthread_record {background: #FFFFFF; padding: 16px; border-radius: 12px;}
    .redthread-status {
        display: inline-block; padding: 7px 12px; border: 1px solid currentColor;
        border-radius: 20px; font-size: 0.9rem; font-weight: 600; line-height: 1.5;
        max-width: 100%; overflow-wrap: anywhere;
    }
    @media (max-width: 640px) {
        .st-key-redthread_header {padding: 16px;}
        .st-key-redthread_header h1 {font-size: 1.8rem;}
        .st-key-redthread_record {padding: 12px;}
    }
    </style>''', unsafe_allow_html=True)


def logo(sidebar=False):
    image = ''
    if LOGO_PATH.is_file():
        # Embed the original bytes; CSS contains the image without cropping or stretching.
        encoded = b64encode(LOGO_PATH.read_bytes()).decode('ascii')
        size = 40 if sidebar else 48
        image = f'<img src="data:image/jpeg;base64,{encoded}" width="{size}" height="{size}" alt="Red Thread logo">'
    title = '<strong>RTA Account Intelligence</strong>' if sidebar else '<h1>RTA Account Intelligence</h1>'
    variant = ' redthread-brand-sidebar' if sidebar else ''
    st.markdown(f'<div class="redthread-brand{variant}">{image}{title}</div>', unsafe_allow_html=True)


def header():
    with st.container(key='redthread_header'):
        logo()
        st.caption('AI-Powered Data Reconciliation & Research')


def status_badge(label):
    if label.startswith('Approved') or label.startswith('Verified'):
        icon, foreground, background = '✓', '#185B40', '#E7F3EC'
    elif label.startswith('Rejected'):
        icon, foreground, background = '×', '#A51219', '#FDECEF'
    elif label == 'Manually Verified':
        icon, foreground, background = '✓', '#174C84', '#EAF1FC'
    else:
        icon, foreground, background = '◷', '#805000', '#FFF4D9'
    st.markdown(f'<span class="redthread-status" style="color:{foreground};background:{background}">'
                f'{icon} {escape(label)}</span>', unsafe_allow_html=True)


def confidence_indicator(confidence):
    if confidence:
        st.caption(f'AI confidence: {confidence} · qualitative evidence assessment; reviewer verification required')
