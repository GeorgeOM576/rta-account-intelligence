"""Static RTA user guide. No workspace, credentials, storage or provider imports."""
from html import escape
import streamlit as st

SUBTITLE = 'From raw account data to verified results in six simple steps.'
STEPS = (
    ('↑', 'Upload Data',
     '- Upload **Master** and **Source** files as CSV or XLSX.\n'
     '- Master is the data to reconcile; Source supplies reference account data.\n'
     '- Check the preview. Excel reads the active worksheet.'),
    ('⚙', 'Configure Reconciliation',
     '- Choose the identifier column for each dataset.\n'
     '- Select the Master comparison field and Source reference field using the existing controls.'),
    ('文', 'Translation Intelligence',
     '- Optional: filter Master or Source, then detect selected or filtered names across pages. Hidden selections are excluded.\n'
     '- Translate when needed; review and approve drafts. **Only approved translations help matching.**\n'
     '- Google actions may incur charges and need separate authorization.'),
    ('⇄', 'Run Reconciliation',
     '- Click **Run automatic local matching**.\n'
     '- RTA uses configured identifiers and eligible name evidence.\n'
     '- Review match statuses and proposed values; uncertain matches need further review.'),
    ('⌕', 'AI Research',
     '- Optional: investigate unresolved accounts with AI and web research.\n'
     '- Check estimated request volume and the authorization notice before starting a batch. Charges may apply.\n'
     '- Recommendations are suggestions, **not approvals**.'),
    ('✓', 'Review & Export',
     '- Open **Review & Approvals** and filter by review status.\n'
     '- Approve, reject or manually verify; Final Value follows human-review safeguards.\n'
     '- Download reviewed results through **Export Results**.'),
)
MATCHES = (
    ('Exact', 'The original identifiers match exactly.'),
    ('Normalized', 'Identifiers match after case and formatting differences are removed.'),
    ('Alias / Relationship', 'A configured alias or company relationship links the names; verify its relevance.'),
    ('Translation-assisted', 'Approved translations suggest a match; verify the entity and field value.'),
    ('Fuzzy candidates', 'Similar names are suggestions, not confirmed matches.'),
    ('Duplicate identifier / Duplicate conflict', 'Repeated identifiers or conflicting Source values need review.'),
    ('Missing identifier / Unresolved', 'The identifier is missing, or no match has been established.'),
)
REVIEWS = (
    ('Intelligence Proposed — Pending Approval', 'A proposed field value awaits review.'),
    ('Manual Review Required', 'No usable proposal is available; investigate or verify manually.'),
    ('Approved', 'A reviewer approved a field value.'),
    ('Rejected', 'A reviewer rejected a proposal.'),
    ('Manually Verified', 'A reviewer explicitly verified a field value.'),
)


def render():
    st.markdown('''<style>
    .st-key-rta_help_intro {background: #FFFFFF; border-left: 3px solid #D71920;
        border-radius: 12px; padding: 16px 20px; margin: 8px 0 24px; color: #081426;}
    .st-key-rta_help_steps [data-testid="stVerticalBlockBorderWrapper"] {border-radius: 14px;}
    .rta-help-heading {display: flex; align-items: center; gap: 12px; margin: 4px 0 12px;
        color: #081426; font-size: 1.15rem; font-weight: 650; line-height: 1.4;}
    .rta-help-icon {display: inline-flex; align-items: center; justify-content: center;
        width: 30px; height: 30px; flex: 0 0 30px; background: #F5F6F8;
        color: #D71920; border-radius: 8px; font-size: 1rem;}
    .st-key-rta_help_steps [data-testid="stMarkdownContainer"] li {margin-bottom: 6px;}
    </style>''', unsafe_allow_html=True)
    st.title('How to Use RTA')
    st.markdown(SUBTITLE)
    with st.container(key='rta_help_intro'):
        st.write('Welcome to RTA. Compare Master and Source account data, translate names, '
                 'match accounts and research uncertain cases—then verify corrections yourself.')
        st.caption('Start with Upload Data in the sidebar. Translation and AI Research are optional.')
    with st.container(key='rta_help_steps'):
        for start in range(0, len(STEPS), 2):
            for column, (number, step) in zip(st.columns(2), enumerate(STEPS[start:start+2], start+1)):
                icon, title, body = step
                with column.container(border=True, key=f'rta_help_step_{number}'):
                    st.caption(f'STEP {number:02d}' + (' · OPTIONAL' if number in (3,5) else ''))
                    st.markdown(f'<div class="rta-help-heading"><span class="rta-help-icon" aria-hidden="true">{escape(icon)}</span>{escape(title)}</div>', unsafe_allow_html=True)
                    st.markdown(body)
    st.subheader('Understanding the results', anchor=False)
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown('**Match Status · How accounts were linked**')
        st.markdown('\n'.join(f'- **{name}:** {meaning}' for name,meaning in MATCHES))
    with right.container(border=True):
        st.markdown('**Review Status · What a reviewer has decided**')
        st.markdown('\n'.join(f'- **{name}:** {meaning}' for name,meaning in REVIEWS))
        st.caption('All is a filter that shows every review status.')
        st.markdown('**Proposed Value** is a suggested field value, not a saved correction.\n\n'
                    '**Final Value** is accepted through explicit approval or manual verification. '
                    'Rejecting a proposal may retain an original value verified earlier.')
    st.subheader('Helpful tips', anchor=False)
    with st.container(border=True):
        st.markdown('- Use consistent identifiers where possible.\n'
                    '- Approve translations before rerunning reconciliation.\n'
                    '- Check uncertain matches carefully.\n'
                    '- AI research is optional and may incur charges.\n'
                    '- Export after completing review.')
