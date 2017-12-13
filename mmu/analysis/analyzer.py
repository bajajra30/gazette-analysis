from mmu.db.handlers.issue import IssueHandler
from mmu.db.handlers.signatures import SignatureHandler
from mmu.db.handlers.signatures import RawSignatureHandler
from mmu.db.handlers.person import PersonHandler
from mmu.automations.researcher import Researcher
from mmu.analysis.pdf_parser import CustomPDFParser
from mmu.utility.helper import Helper
import re
import json
from timeit import default_timer as timer

class Analyzer:

    def __init__(self):
        self.__issue_handler = IssueHandler()
        self.__pdf_analyzer = CustomPDFParser()
        self.__signature_handler = SignatureHandler()
        self.__person_handler = PersonHandler()
        self.__researcher = Researcher()
        self.__raw_signature_handler = RawSignatureHandler()

        # Compile regular expressions that will be used a lot
        self.__illegal_chars = re.compile(r"\d+")
        self.__camel_case_patteren = re.compile("([α-ω])([Α-Ω])")
        self.__final_s_pattern = re.compile("(ς)([Α-Ωα-ωά-ώ])")
        self.__u_pattern = re.compile("(ύ)(και)")

    # Checks whether or not a string indicates that parsing should stop.
    def is_break_point(self, word):
        if len(word) == 0:
            return False
        elif self.__illegal_chars.search(word):
            return True
        else:
            return False

    # Finds all occurences of a substring in a string
    # @return The indexes of all matched substrings.
    def find_all(self, key, string):
        matches = []
        start = 0
        searching = True
        while searching:
            index = string.find(key, start)

            if index == -1:
                searching = False
            else:
                matches.append(index)
                start = index + 1

        return matches

    # Formats roles extracted from pdfs. Specifically, splits separate words that are stuck together
    def format_role(self, text):
        parts = text.split(" ")

        final_word = ""
        for part in parts:
            split = self.__camel_case_patteren.sub(r'\1 \2', part).split()

            # If no TitleCase or camelCase was found then we address the possibility of a final s inside a word
            if len(split) == 1:
                split = self.__final_s_pattern.sub(r'\1 \2', part).split()

            # If no TitleCase or camelCase was found then we address the possibility of a final s inside a word
            if len(split) == 1:
                split = self.__u_pattern.sub(r'\1 \2', part).split()

            for word in split:
                final_word += word + " "

        # Returns the word without trailing spaces
        return final_word.strip()

    # Returns a list of valid start keys for a certain year's format
    def get_start_keys(self, year):
        if year == "2017":
            return ["Οι Υπουργοί\n", "Οι Αναπληρωτές Υπουργοί\n"]
        else:
            return ["ΟΙ ΥΠΟΥΡΓΟΙ\n", "ΟΙ ΑΝΑΠΛΗΡΩΤΕΣ ΥΠΟΥΡΓΟΙ\n"]


    # Analyzes the text from the pdf files to extract all signatures
    def extract_signatures_from_text(self, text, year):
        start_keys = self.get_start_keys(year)
        end_key = "Θεωρήθηκε και τέθηκε η Μεγάλη Σφραγίδα του Κράτους."
        starting_indexes = []

        for key in start_keys:
            starting_indexes += self.find_all(key, text)

        if not starting_indexes:
            starting_indexes = [m.start() for m in Helper.date_match(year).finditer(text)]

        # Ending indexes are useful when available, but availability is not guaranteed
        ending_indexes = self.find_all(end_key, text)

        # @todo: Find ministry council's members from pdf text (Τα Μέλη - Μέλη Υπουργικού Συμβουλίου)
        persons = []
        for key, index in enumerate(starting_indexes):
            # Indicates whether or not the substring contains non-required information after the signatures
            # Is True when a valid ending index has been found
            end = (key < len(ending_indexes) and ending_indexes[key] > index)

            if end:
                to = ending_indexes[key]
                substring = text[index:to]
            else:
                substring = text[index:]

            words = re.split("\n|\s{2,2}", substring)

            # Iterates through words after the starting key
            role = ""
            temp_name = ""
            skip_steps = 0

            for key, word in enumerate(words[1:]):

                # If a valid ending point has not been found, then the first non-word will surely indicate the end of
                # the signatures.
                if not end and self.is_break_point(word):
                    break

                # Skips an element if required
                if skip_steps > 0:
                    skip_steps -= 1
                    continue

                if len(word) > 3 and word.upper() == word:

                    if not role:
                        temp_name = word.strip()
                    else:
                        persons.append({"role" : self.format_role(role), "name" : word.strip()})

                    # Reset role for the next one
                    role = ""

                elif temp_name and len(word) > 3:
                    temp_role = ""
                    current_key = key + 1

                    while current_key < len(words) - 1:
                        if words[current_key] == "":
                            break
                        else:
                            temp_role += words[current_key] + " "
                            current_key += 1
                    skip_steps = current_key - (key + 2)
                    persons.append({'role' : temp_role.strip(), 'name': temp_name})
                    temp_name = ""
                else:
                    role += word

            if temp_name and role:
                persons.append({"role": self.format_role(role), "name": temp_name})

        return persons


    def load_signature_from_issue(self, issue_id, person_name):
        conditions = {'issue_id' : [issue_id]}
        return self.__signature_handler.load_all_by_person_name(person_name, conditions=conditions)

    # Returns information about a person that's saved in the db. If no information is saved, then
    # all required information is found through the researcher.
    def load_person_by_name(self, name):
        normalized_name = Helper.normalize_greek_name(name)
        person = self.__person_handler.load_by_name(normalized_name)

        if not person:
            self.__researcher.research_person(name)
            person = self.__person_handler.load_by_name(normalized_name)

        return person

    # Loads a raw signature by its issue title and by the person's name
    def load_raw_signature(self, issue_title, person_name):
        conditions = {'issue_title': [issue_title], 'person_name': [person_name]}
        return self.__raw_signature_handler.load_one(conditions=conditions)

    def start_signature_extraction(self):
        # Loads all issues not yet analyzed
        issues = self.__issue_handler.load_all({'analyzed' : [0], 'type': ['Α'],
                                                'date': ['2017-01-01 00:00:00', '>=']})

        if not issues or issues[0] == None:
            return

        for issue in issues:
            issue_id = issue['id']
            issue_file = issue['file']
            issue_number = issue['number']
            issue_title = issue['title']
            issue_date = issue['date']

            if issue_file == 'N/A':
                continue

            pdf_text = self.__pdf_analyzer.get_pdf_text(issue_file)
            pdf_images = self.__pdf_analyzer.get_pdf_images(issue_file, issue_id)

            if pdf_text:
                # print("Extracting signatures from issue {}".format(issue_title))
                year = issue_date[0:4]
                start = timer()
                text_signatures = self.extract_signatures_from_text(pdf_text, year)
                end = timer()
                print("{} seconds elapsed for extracting signatures from the text.".format(end - start))
                if text_signatures:
                    print("{} signatures found.".format(len(text_signatures)))
                    print(issue_title, text_signatures)
                    raw_signatures = []
                    start = timer()
                    for signature in text_signatures:
                        name = signature['name']
                        role = signature['role']
                        person = self.load_person_by_name(name)
                        db_signature = self.load_signature_from_issue(issue_id, name)

                        if not db_signature:

                            data = json.dumps(signature)
                            person_id = person['id']
                            self.__signature_handler.create(person_id, issue_id, data)

                        person_name = person['name']


                        raw_signatures.append({'person_name': Helper.normalize_greek_name(person_name),
                                               'role': Helper.normalize_greek_name(role),
                                               'issue_title': issue_title,
                                               'issue_date': issue_date})

                    self.__raw_signature_handler.create_multiple(raw_signatures)
                    end = timer()
                    print("{} to save all the stuff.".format(end - start))
                else:
                    print(issue_title, " has no relevant signatures.")
            self.__issue_handler.set_analyzed(issue_id)

    def start_analysis(self, conditions = None):
        all_signatures = self.__raw_signature_handler.load_all(conditions)
        print(all_signatures)

        # Gets all the signatures grouped by name
        all_names = self.__raw_signature_handler.load_all(conditions, 'person_name')
        print(len(all_names))

        for signature in all_names:
            name = signature['person_name']
            person_signatures = self.__raw_signature_handler.load_all_by_person_name(name)
            role_titles = {}
            signature['ministry'] = self.find_ministry_name_from_role(signature['role'])

            # Code snippet that finds people's signatures without the middle initial
            # name_parts = name.split(" ")
            # if len(name_parts) > 2:
            #     first_name = name_parts[0]
            #     last_name = name_parts[len(name_parts) - 1]
            #     similar_name_conditions = {'person_name': ["{f}%{l}".format(f=first_name, l=last_name), 'LIKE'],
            #                                'raw_signatures.person_name': [name, '!=']}
            #     same_person_different_name = self.__raw_signature_handler.load_all(conditions=similar_name_conditions)
            #     if (same_person_different_name):
            #         print('Test', same_person_different_name)

            for sig in person_signatures:

                if not sig['role'] in role_titles:
                    role_titles[sig['role']] = 0

                role_titles[sig['role']] += 1

            if len(role_titles) > 1:
                correct_role = max(role_titles, key=role_titles.get)
                update_conditions = conditions if conditions else {}
                update_conditions['person_name'] = [name]
                self.__raw_signature_handler.update(params={'role': correct_role}, conditions=conditions)

    def find_ministry_name_from_role(self, role):
        role_parts = role.split(" ")
        # stop_index = 0
        current_title = ""
        # We go through the words inside the role backwards. As long as it produces the same amount of results it's
        # still the ministry title.
        prev_num = -1
        for part in reversed(role_parts):
            current_title = part + " " + current_title
            conditions = {'role': ['%' + current_title, 'LIKE']}
            results = self.__raw_signature_handler.load_all(conditions)
            if prev_num != -1 and prev_num != len(results):
                break
        if current_title != 'ΠΡΩΘΥΠΟΥΡΓΟΣ':
            current_title = current_title.replace("ΥΦΥΠΟΥΡΓΟΣ", "").replace("ΥΠΟΥΡΓΟΣ", "").replace("ΑΝΑΠΛΗΡΩΤΗΣ", "").strip()
        return current_title
