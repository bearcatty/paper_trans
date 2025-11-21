from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import red, blue

def create_test_pdf(filename):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Page 1
    # Header
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 30, "Header: Confidential Document")
    
    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 100, "Artificial Intelligence Overview")
    
    # Body Text
    c.setFont("Helvetica", 12)
    text = "Artificial intelligence (AI) is intelligence demonstrated by machines, as opposed to the natural intelligence displayed by animals including humans."
    c.drawString(50, height - 150, text)
    
    # Image (Draw a rect to simulate image)
    c.setFillColor(red)
    c.rect(50, height - 400, 200, 150, fill=1)
    c.setFillColor(blue)
    
    # More Text
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 450, "Figure 1: A red rectangle representing an image.")
    
    # Footer
    c.setFont("Helvetica", 10)
    c.drawString(50, 30, "Footer: Page 1 of 1")
    
    c.showPage()
    c.save()

if __name__ == "__main__":
    create_test_pdf("data/test_input.pdf")
    print("Created data/test_input.pdf")
