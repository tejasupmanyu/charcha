import json

class PresentationParser:
    def __init__(self, presentation):
        self.presentation = presentation

    def text_in_slide(self):
        slides = self.presentation['slides']
        for slide in slides:
            slide_id = slide['objectId']
            for pe in slide['pageElements']:
                if 'shape' in pe:
                    shape = pe['shape']
                    if shape['shapeType'] == 'TEXT_BOX' and 'text' in shape and 'textElements' in shape['text']:
                        for te in shape['text']['textElements']:
                            if 'textRun' in te:
                                yield (slide_id, te['textRun']['content'])

    def non_empty_text_in_slide(self):
        return filter(lambda s: s[1].strip() != '', self.text_in_slide())

    def slide_and_hasher(self):
        prev_slide_id = None
        for slide_id, text in self.non_empty_text_in_slide():
            if prev_slide_id != slide_id:
                prev_slide_id = slide_id
                yield (slide_id, text.strip())
            else:
                continue

if __name__ == '__main__':
    profile_slide = "/home/sri/hasher-profile-slide.json"
    with open(profile_slide) as f:
        presentation = PresentationParser(json.load(f))
    
    for slide_id, text in presentation.slide_and_hasher():
        print(text)

