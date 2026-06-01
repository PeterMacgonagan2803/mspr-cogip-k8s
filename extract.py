import PyPDF2
from docx import Document

pdf_path = r"c:\Users\PC-HUGO\MSPR2\25-26 I2 EISI - Sujet MSPR TPRE961 (Infra).pdf"
docx_path = r"c:\Users\PC-HUGO\MSPR2\MSPR_TPRE961_Dossier_Rendu_Final 2.docx"

try:
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        pdf_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pdf_text.append(text)
        with open('sujet.txt', 'w', encoding='utf-8') as out:
            out.write('\n'.join(pdf_text))
except Exception as e:
    print(f"Error reading PDF: {e}")

try:
    doc = Document(docx_path)
    docx_text = [p.text for p in doc.paragraphs]
    with open('rendu.txt', 'w', encoding='utf-8') as out:
        out.write('\n'.join(docx_text))
except Exception as e:
    print(f"Error reading DOCX: {e}")

print("Extraction complete.")
