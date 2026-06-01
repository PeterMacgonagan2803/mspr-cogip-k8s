from docx import Document

docx_path = r"c:\Users\PC-HUGO\MSPR2\MSPR_TPRE961_Dossier_Rendu_Final 2.docx"
doc = Document(docx_path)

images_count = 0
for rel in doc.part.rels.values():
    if "image" in rel.target_ref:
        images_count += 1

print(f"Number of images in DOCX: {images_count}")
