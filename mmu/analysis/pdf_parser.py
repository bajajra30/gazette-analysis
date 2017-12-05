import os
import io

from subprocess import call
from PIL import Image

from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage

from timeit import default_timer as timer

class CustomPDFParser:

    def __init__(self):
        self.__project_path = os.getcwd()
        self.rsrcmgr = PDFResourceManager()
        self.retstr = io.StringIO()
        self.laparams = LAParams()
        self.codec = 'utf-8'
        self.device = TextConverter(self.rsrcmgr, self.retstr, codec=self.codec, laparams=self.laparams)
        self.interpreter = PDFPageInterpreter(self.rsrcmgr, self.device)

    def get_pdf_text(self, file_name):
        try:
            text = self.convert_pdf_to_txt(file_name)
        except FileNotFoundError:
            print("The file with the name {} was not found.".format(file_name))
            text = ""
        return text

    # Uses libpoppler's pdfimages tool to extract all images from the pdf and then uses PIL to convert from ppm to jpg
    # @return A list of image paths extracted from this pdf
    def get_pdf_images(self, file_name, id):
        file_path = self.__project_path + file_name
        directory = self.__project_path + '\\images\\' + str(id)
        images = []
        if not os.path.exists(directory):
            os.makedirs(directory)
            call(['pdfimages', file_path, directory +  "\\" + str(id)])

        files = os.listdir(directory)

        for file in files:
            image_path = os.path.join(directory, file)
            # Convert .ppm images to jpg
            if '.ppm' in image_path:
                image = Image.open(image_path)
                image_path = image_path.replace(".ppm", ".jpg")
                image.save(image_path)
            images.append(image_path)



        return images

    def convert_pdf_to_txt(self, path):
        start = timer()
        fp = open(path, 'rb')

        password = ""
        maxpages = 0
        caching = True
        pagenos = set()

        for page in PDFPage.get_pages(fp, pagenos, maxpages=maxpages,
                                      password=password,
                                      caching=caching,
                                      check_extractable=True):
            self.interpreter.process_page(page)

        text = self.retstr.getvalue()

        # Close the pdf file
        fp.close()

        end = timer()
        print(end - start)
        return text

    # Closes the io elements used in here to avoid a resource leak
    def close(self):
        self.device.close()
        self.retstr.close()