from docx import Document

docx_path = r"c:\Users\PC-HUGO\MSPR2\MSPR_TPRE961_Dossier_Rendu_Final 2.docx"
doc = Document(docx_path)

with open('rendu_tables.txt', 'w', encoding='utf-8') as f:
    for i, table in enumerate(doc.tables):
        f.write(f"--- TABLE {i} ---\n")
        for row in table.rows:
            f.write(" | ".join([cell.text.replace('\n', ' ') for cell in row.cells]) + "\n")
