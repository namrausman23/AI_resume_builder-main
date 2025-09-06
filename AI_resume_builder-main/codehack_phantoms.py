from flask import Flask, request, jsonify, send_file, render_template, request
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os, uuid, mimetypes, subprocess
import google.generativeai as genai
import docx2txt
import fitz  # PyMuPDF
import shutil
from pdflatex import PDFLaTeX

app = Flask(__name__)
CORS(app)
load_dotenv()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

def extract_text_from_resume(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        text = ""
        doc = fitz.open(filepath)
        all_links = []
        for page in doc:
            text += page.get_text()
            # Find all hyperlink objects on the page
            page_links = page.get_links()
            for link in page_links:
                # Add the URL to our list if it exists
                if 'uri' in link:
                    all_links.append(link['uri'])

        # Append the found links to the end of the extracted text
        # This makes the links available to the Gemini model
        if all_links:
            text += "\n\n--- DETECTED HYPERLINKS ---\n"
            text += "The following hyperlinks were found in the document. Please associate them with the correct projects or sections.\n"
            # Use a set to avoid duplicate links
            for link_url in sorted(list(set(all_links))):
                text += f"- {link_url}\n"
        return text
    elif ext == ".docx":
        # Note: python-docx has limited support for extracting hyperlinks.
        # This part of the function remains unchanged.
        return docx2txt.process(filepath)
    else:
        return "Unsupported format"

def call_gemini_for_latex(resume_text, job_description):
    try:
        with open("template.tex", "r") as f:
            latex_template = f.read()
    except FileNotFoundError:
        return "LaTeX template file (template.tex) not found."

    prompt = fr"""
You are a LaTeX resume expert.

Your job is to:
- Read the provided LaTeX template and ONLY fill in the content. Do not alter the template's structure, packages, or existing commands.
- Use the content from the provided resume and optimize it to align with the job description. The goal is to make the resume highly relevant to the job description.
- **Do not include any N/A placeholders.** Instead, if a section from the template is not relevant or if the required information is not available in the resume, you must omit the entire section and its corresponding title (`\section{...}`).
- Ensure the generated content fits seamlessly into the template and always returns a complete, valid LaTeX document that compiles without errors.
- **VERY IMPORTANT: Your output MUST be pure LaTeX code.** Do NOT wrap the code in markdown (e.g., ```latex) or include any extra text, explanations, or comments outside of standard LaTeX comments (lines beginning with %).
- **Handle special characters properly.** Escape the following characters with a backslash: `&`, `%`, `$`, `#`, `_`, '{', '}', `~`. **For a literal ampersand in a section title or list item (e.g., "Programming & Web Technologies"), you MUST use `\&`.**
- For date ranges and similar uses, replace a single hyphen (`-`) with a double hyphen (`--`) to create an en dash, which is the correct LaTeX symbol for ranges.
- **Handle all links and URLs using the template's commands.**
    - For projects, certifications, or any other section with links, use the `\href` command with **"Link"** as the display text, but always extract and preserve the original link from the resume. For example, if the resume contains a project named "AI Resume Builder" with the link `https://github.com/user/resume`, use: `\href{{https://github.com/user/resume}}{{Link}}`.
    - For the header section, use `\hrefWithoutArrow` for the LinkedIn profile, email, and phone number. 
    
    - If the original display text for the link is short and meaningful (e.g., "Portfolio", "GitHub Repo"), it's okay to use that instead of "Link", otherwise default to "Link".

- Ensure the output is a complete LaTeX document, starting with `\documentclass` and ending with `\end{{document}}`.


========
TEMPLATE:
{latex_template}

========
JOB DESCRIPTION:
{job_description}

========
RESUME:
{resume_text}

Now, return the complete, valid, and compilable LaTeX code based on the TEMPLATE, filled with content from the RESUME, and optimized for the JOB DESCRIPTION.
"""

    response = model.generate_content(prompt)
    generated_latex_code = response.text.strip()

    # The model is instructed to return the full LaTeX code based on the template
    # No additional insertion logic is needed here if the model follows instructions.
    # We can add a basic check to ensure the response looks like LaTeX
    if not generated_latex_code.startswith('\\documentclass') and not '\\begin{document}' in generated_latex_code:
         print("Warning: Gemini did not return a full LaTeX document. Attempting to use original template with generated content.")
         # Fallback to original insertion logic if the model doesn't return the full template
         start_marker = "% --- Content will be generated here by the model ---"
         end_marker = "% --- End of generated content ---"
         if start_marker in latex_template and end_marker in latex_template:
             before = latex_template.split(start_marker)[0] + start_marker + "\n"
             after = "\n" + end_marker + latex_template.split(end_marker)[1]
             # Assuming the model still generated only the content part in this case
             content_part = response.text.strip() # Use original response text
             generated_latex_code = before + content_part + after
         else:
             return "LaTeX template is missing the required placeholder comments for fallback.", 500

    if "begin{document}" in generated_latex_code and "\\begin{document}" not in generated_latex_code:
        generated_latex_code = generated_latex_code.replace("begin{document}", "\\begin{document}")
    if "end{document}" in generated_latex_code and "\\end{document}" not in generated_latex_code:
        generated_latex_code = generated_latex_code.replace("end{document}", "\\end{document}")

    return generated_latex_code



def latex_to_pdf(latex_code, output_filename="resume"):
    tex_file = f"{output_filename}.tex"

    # Write the LaTeX code to a .tex file
    with open(tex_file, "w") as f:
        f.write(latex_code)

    try:
        # Create PDFLaTeX object from the written tex file
        pdfl = PDFLaTeX.from_texfile(tex_file)
        
        # Generate PDF (set keep_pdf_file=True to save the PDF file)
        pdf_binary, log_output, completed_process = pdfl.create_pdf(
            keep_pdf_file=True,
            keep_log_file=True
        )

        # Optionally, write the binary PDF to a file explicitly
        pdf_file = f"{output_filename}.pdf"
        with open(pdf_file, "wb") as pdf_out:
            pdf_out.write(pdf_binary)

        return pdf_file
    except Exception as e:
        return f"PDF generation failed: {str(e)}"



@app.route('/')
def home():
    return render_template('index.html')

@app.route("/process", methods=["POST"])
def process_resume():
    file = request.files['resume']
    job_desc = request.form['job_description']

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    resume_text = extract_text_from_resume(path)
    if resume_text == "Unsupported format":
        return "Only PDF or DOCX allowed", 400

    latex_code = call_gemini_for_latex(resume_text, job_desc)
    if "LaTeX template file (template.tex) not found." in latex_code:
        return latex_code, 500 # Return an error if the template file is not found

    output_pdf = latex_to_pdf(latex_code)
    
    # Check if PDF generation failed
    if not os.path.isfile(output_pdf):
        return f"PDF generation failed: {output_pdf}", 500

    # Use the uploaded resume's base name for the download name
    base_name, _ = os.path.splitext(filename)
    download_name = f"{base_name}_updated.pdf"
    return send_file(output_pdf, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    app.run(debug=True)

