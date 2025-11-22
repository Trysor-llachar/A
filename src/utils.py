import pandas as pd
from io import StringIO
import pytesseract
from mss import mss
import numpy as np
from PyQt6.QtCore import QRect

def find_text_location_in_df(df, text_to_find):
    """Finds the bounding box of a sequence of words in an OCR DataFrame."""
    words = text_to_find.split()
    if not words:
        return None

    df['text_str'] = df['text'].astype(str)
    for i in range(len(df) - len(words) + 1):
        chunk = df.iloc[i:i + len(words)]
        sequence = " ".join(chunk['text_str'])
        if sequence == text_to_find:
            x_min = chunk['left'].min()
            y_min = chunk['top'].min()
            x_max = (chunk['left'] + chunk['width']).max()
            y_max = (chunk['top'] + chunk['height']).max()
            return QRect(int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))
    return None

def find_text_on_screen(text_to_find):
    """Performs a full-screen OCR to find the location of text."""
    with mss() as sct:
        sct_img = sct.grab(sct.monitors[1])
        img = np.array(sct_img)
        ocr_df = pd.read_csv(StringIO(pytesseract.image_to_data(img)), sep='\t')

    return find_text_location_in_df(ocr_df, text_to_find)
