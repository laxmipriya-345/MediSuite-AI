import os
import json
import re
from reportlab.lib.units import inch
from reportlab.lib import colors
from fuzzywuzzy import fuzz, process
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from PDFBuilder import PDFBuilder
from llm_interface import LLMInterface

class MedicalCodingAgent:
    def __init__(self, llm: LLMInterface, icd10_data_path="ICD10.json", cpt4_data_path="CPT4.json", pdf_builder=None,
                 tesseract_cmd=None, poppler_path=None):
        self.llm = llm  # Use the LLM interface

        # Configure Tesseract OCR path
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # Configure Poppler path
        self.poppler_path = poppler_path

        # Load ICD-10 and CPT-4 data
        self.icd10_data = self.load_icd10_data(icd10_data_path)
        self.cpt4_data = self.load_cpt4_data(cpt4_data_path)

        # Initialize other attributes
        self.patient_info = {}
        self.diagnoses = []
        self.procedures = []
        self.matched_icd10_codes = []
        self.matched_cpt4_codes = []
        self.conversation_history = []
        self.current_state = "greeting"
        self.summary_mode = False
        self.clinical_info = {}

        # Define essential patient info fields
        self.essential_info_fields = {
            "name": "full name",
            "dob": "date of birth",
            "gender": "gender",
            "insurance": "insurance provider",
            "policy": "insurance ID"
        }

        # Inject PDFBuilder instance
        self.pdf_builder = pdf_builder or PDFBuilder("default_claim.pdf")

    def load_icd10_data(self, data_path):
        """Load ICD-10 codes from json file"""
        try:
            with open(data_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"Error loading ICD-10 data: {e}")
            # Return empty list if file loading fails
            return []
    
    def load_cpt4_data(self, data_path):
        """Load CPT-4 codes from json file"""
        try:
            with open(data_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"Error loading CPT-4 data: {e}")
            # Return empty list if file loading fails
            return []
    
    def start_conversation(self):
        """Begin the conversation with the user"""
        self.add_to_history("system", "You are an AI medical coding assistant that helps healthcare providers accurately code diagnoses with ICD-10 codes, procedures with CPT-4 codes, and generate insurance claim forms.")
        
        # Initial greeting
        greeting = "Hello! I'm your AI medical coding assistant. I can help you code patient diagnoses and procedures, then generate insurance claims. Would you like to:\n1. Start with guided mode (I'll help you step by step)\n2. Use summary mode (provide all information at once)\n3. Upload a PDF/JPG document (I'll extract information from your document)"
        self.add_to_history("assistant", greeting)
        print("Assistant:", greeting)
        
        # Start the conversation loop
        self.conversation_loop()
    
    def conversation_loop(self):
        """Main conversation loop for the agent"""
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:  # Handle empty inputs
                    print("Assistant: I didn't catch that. Could you please repeat?")
                    continue
                    
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("Assistant: Thank you for using the Medical Coding Assistant. Goodbye!")
                    break
                    
                self.add_to_history("user", user_input)
                
                # Process based on current state
                if self.current_state == "collecting_patient_info":
                    self.collect_patient_info(user_input)
                elif self.current_state == "collecting_clinical_notes":
                    self.collect_clinical_notes(user_input)
                elif self.current_state == "confirming_codes":
                    self.confirm_codes(user_input)
                elif self.current_state == "reviewing_claim":
                    self.review_claim(user_input)
                elif self.current_state == "post_claim_menu":
                    self.handle_post_claim_menu(user_input)
                elif self.current_state == "collecting_summary":
                    self.collect_summary(user_input)
                elif self.current_state == "code_lookup":
                    self.code_lookup(user_input)
                elif self.current_state == "processing_document":
                    self.process_document(user_input)
                else:
                    # Default handling using GPT for flexible conversation
                    self.handle_default_conversation(user_input)
            except EOFError:
                print("\nInput stream ended. Exiting...")
                break
            except KeyboardInterrupt:
                print("\nProgram interrupted. Exiting...")
                break
            except Exception as e:
                print(f"Error in conversation loop: {str(e)}")
                print("Assistant: Sorry, I encountered an error. Let's continue.")
    
    def add_to_history(self, role, content):
        """Add a message to the conversation history"""
        self.conversation_history.append({"role": role, "content": content})
    
    def generate_llm_response(self, specific_prompt=None):
        """Generate a response using the LLM interface."""
        try:
            response = self.llm.generate_response(self.conversation_history, specific_prompt)
            self.add_to_history("assistant", response)
            print("Assistant:", response)
            return response
        except Exception as e:
            error_message = f"I apologize, but I encountered an error: {str(e)}. Please try again."
            self.add_to_history("assistant", error_message)
            print("Assistant:", error_message)
            return error_message
    
    def collect_patient_info(self, user_input):
        """Collect and parse patient information"""
        # Extract potential patient info using GPT
        system_prompt = """
        Extract patient information from the user's message. 
        Look for:
        - Full name
        - Date of birth
        - Gender
        - Address (optional)
        - Phone number (optional)
        - Insurance provider
        - Insurance ID
        - Group number (optional)
        
        Format your response as JSON with keys: name, dob, gender, address, phone, insurance, policy, group.
        For any missing information, use null or empty string.
        """
        
        response = self.generate_llm_response(system_prompt)
        
        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            json_pattern = r'\{.*\}'
            json_match = re.search(json_pattern, response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                extracted_info = json.loads(json_str)
                
                # Update patient info with extracted data
                for key, value in extracted_info.items():
                    if value not in [None, "", "null"]:
                        self.patient_info[key] = value
            
            # Check if we have all essential information
            missing_fields = []
            for field, description in self.essential_info_fields.items():
                if field not in self.patient_info or not self.patient_info[field]:
                    missing_fields.append(description)
            
            if missing_fields:
                # Ask for missing essential information
                fields_str = ", ".join(missing_fields)
                response = f"I still need the following essential information: {fields_str}. Please provide these details."
                self.add_to_history("assistant", response)
                print("Assistant:", response)
            else:
                # Move to collecting clinical notes
                self.current_state = "collecting_clinical_notes"
                response = "Thank you for providing the patient information. Now, please share the clinical notes or medical documentation. I'll extract diagnosis (ICD-10) and procedure (CPT-4) codes from them."
                self.add_to_history("assistant", response)
                print("Assistant:", response)
                
        except Exception as e:
            print(f"Error parsing patient info: {e}")
            response = "I had trouble processing that information. Could you please provide the patient details again, clearly specifying their name, date of birth, gender, insurance provider, and policy number?"
            self.add_to_history("assistant", response)
            print("Assistant:", response)
    
    def collect_clinical_notes(self, user_input):
        """Collect and process clinical notes to extract diagnoses and procedures"""
        # First, try to extract diagnoses (ICD-10)
        icd10_system_prompt = """
        Extract potential medical diagnoses from the clinical notes. 
        Focus on conditions, diseases, symptoms, or health issues mentioned.
        Format your response as a list of diagnoses, one per line.
        """
        
        # Extract diagnoses
        diagnoses_response = self.generate_llm_response(icd10_system_prompt)
        
        # Try to parse diagnoses from the response
        extracted_diagnoses = []
        for line in diagnoses_response.split('\n'):
            # Skip empty lines or lines that aren't diagnoses
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("Assistant:") and not clean_line.startswith("Here are"):
                # Remove any list markers (1., -, *, etc.)
                diagnosis = re.sub(r'^[\d\-\*\.\s]+', '', clean_line).strip()
                if diagnosis:
                    extracted_diagnoses.append(diagnosis)
        
        # Find matching ICD-10 codes for each diagnosis
        self.diagnoses = extracted_diagnoses
        all_icd10_matches = []
        
        for diagnosis in self.diagnoses:
            matches = self.find_matching_icd10_codes(diagnosis)
            if matches:
                all_icd10_matches.append({
                    "diagnosis": diagnosis,
                    "matches": matches[:5]  # Top 5 matches
                })
        
        # Now extract procedures (CPT-4)
        cpt4_system_prompt = """
        Extract potential medical procedures from the clinical notes.
        Focus on treatments, surgeries, tests, or other medical services performed.
        Format your response as a list of procedures, one per line.
        """
        
        # Extract procedures
        procedures_response = self.generate_llm_response(cpt4_system_prompt)
        
        # Try to parse procedures from the response
        extracted_procedures = []
        for line in procedures_response.split('\n'):
            # Skip empty lines or lines that aren't procedures
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("Assistant:") and not clean_line.startswith("Here are"):
                # Remove any list markers (1., -, *, etc.)
                procedure = re.sub(r'^[\d\-\*\.\s]+', '', clean_line).strip()
                if procedure:
                    extracted_procedures.append(procedure)
        
        # Find matching CPT-4 codes for each procedure
        self.procedures = extracted_procedures
        all_cpt4_matches = []
        
        for procedure in self.procedures:
            matches = self.find_matching_cpt4_codes(procedure)
            if matches:
                all_cpt4_matches.append({
                    "procedure": procedure,
                    "matches": matches[:5]  # Top 5 matches
                })
        
        # Store current matches for confirmation
        self.current_icd10_matches = all_icd10_matches
        self.current_cpt4_matches = all_cpt4_matches
        
        # Build response with matched codes
        response = "Based on the clinical notes, I've identified the following:\n\n"
        
        if all_icd10_matches:
            response += "DIAGNOSES:\n"
            for i, item in enumerate(all_icd10_matches, 1):
                response += f"{i}. For '{item['diagnosis']}', I found these ICD-10 codes:\n"
                for j, match in enumerate(item['matches'], 1):
                    response += f"   {chr(96+j)}. {match['code']} - {match['disease']}\n"
        else:
            response += "I couldn't identify any clear diagnoses for ICD-10 coding.\n"
        
        response += "\n"
        
        if all_cpt4_matches:
            response += "PROCEDURES:\n"
            for i, item in enumerate(all_cpt4_matches, 1):
                response += f"{i}. For '{item['procedure']}', I found these CPT-4 codes:\n"
                for j, match in enumerate(item['matches'], 1):
                    response += f"   {chr(96+j)}. {match['code']} - {match['procedure']}\n"
        else:
            response += "I couldn't identify any clear procedures for CPT-4 coding.\n"
        
        response += "\nPlease confirm the codes by typing the corresponding numbers and letters (e.g., '1a, 2c, 3b' for diagnoses and '1B, 2A' for procedures (Case sensitive)). Or type 'none' if none of the suggested codes are appropriate."
        
        self.add_to_history("assistant", response)
        print("Assistant:", response)
        self.current_state = "confirming_codes"
    
    def find_matching_icd10_codes(self, diagnosis_text):
        """Find ICD-10 codes that match the given diagnosis text"""
        matches = []
        
        # Using fuzzy matching to find potential matches
        for code_entry in self.icd10_data:
            disease_score = fuzz.token_set_ratio(diagnosis_text.lower(), code_entry["disease"].lower())
            category_score = fuzz.token_set_ratio(diagnosis_text.lower(), code_entry["category"].lower())
            
            # Use the higher of the two scores
            best_score = max(disease_score, category_score)
            
            if best_score > 70:  # Threshold for considering it a match
                matches.append({
                    "code": code_entry["code"],
                    "disease": code_entry["disease"],
                    "category": code_entry["category"],
                    "score": best_score
                })
        
        # Sort by score in descending order
        matches.sort(key=lambda x: x["score"], reverse=True)
        
        return matches
    
    def find_matching_cpt4_codes(self, procedure_text):
        """Find CPT-4 codes that match the given procedure text"""
        matches = []
        
        # Using fuzzy matching to find potential matches
        for code_entry in self.cpt4_data:
            procedure_score = fuzz.token_set_ratio(procedure_text.lower(), code_entry["procedure"].lower())
            
            if procedure_score > 70:  # Threshold for considering it a match
                matches.append({
                    "code": code_entry["code"],
                    "procedure": code_entry["procedure"],
                    "score": procedure_score
                })
        
        # Sort by score in descending order
        matches.sort(key=lambda x: x["score"], reverse=True)
        
        return matches
    
    def confirm_codes(self, user_input):
        """Confirm selected ICD-10 and CPT-4 codes"""
        if user_input.lower() == "none":
            # User doesn't want any of the suggested codes
            response = "No problem. I'll generate a claim form without any coding. Would you like to provide alternative codes manually?"
            self.add_to_history("assistant", response)
            print("Assistant:", response)
        else:
            # Parse user selections
            try:
                # Split input into diagnosis and procedure sections
                parts = user_input.split(',')
                
                # Process ICD-10 selections (diagnoses)
                icd10_pattern = r'(\d+)([a-zA-Z])'
                for part in parts:
                    match = re.search(icd10_pattern, part.strip())
                    if match and len(match.groups()) == 2:
                        diagnosis_idx = int(match.group(1)) - 1
                        code_letter = match.group(2).lower()
                        code_idx = ord(code_letter) - 97
                        
                        if 0 <= diagnosis_idx < len(self.current_icd10_matches):
                            diagnosis_matches = self.current_icd10_matches[diagnosis_idx]
                            if 0 <= code_idx < len(diagnosis_matches["matches"]):
                                selected_code = diagnosis_matches["matches"][code_idx]
                                if selected_code not in self.matched_icd10_codes:
                                    self.matched_icd10_codes.append(selected_code)
                
                # Process CPT-4 selections (procedures)
                cpt4_pattern = r'(\d+)([A-Z])'
                for part in parts:
                    match = re.search(cpt4_pattern, part.strip())
                    if match and len(match.groups()) == 2:
                        procedure_idx = int(match.group(1)) - 1
                        code_letter = match.group(2).lower()
                        code_idx = ord(code_letter) - 97
                        
                        if 0 <= procedure_idx < len(self.current_cpt4_matches):
                            procedure_matches = self.current_cpt4_matches[procedure_idx]
                            if 0 <= code_idx < len(procedure_matches["matches"]):
                                selected_code = procedure_matches["matches"][code_idx]
                                if selected_code not in self.matched_cpt4_codes:
                                    self.matched_cpt4_codes.append(selected_code)
                
                # Now generate the claim form
                response = "Thank you for confirming the codes. I'll now generate a claim form with the selected codes. Please wait..."
                self.add_to_history("assistant", response)
                print("Assistant:", response)
                
                # Generate the claim form
                filename = self.generate_cms1500_pdf()
                
                # Move to reviewing the claim
                self.current_state = "reviewing_claim"
                
                response = f"I've generated a CMS-1500 claim form and saved it as '{filename}'. Here's a preview of the claim details:\n\n"
                
                # Patient info
                response += "PATIENT INFORMATION:\n"
                for key, value in self.patient_info.items():
                    if value:  # Only include non-empty fields
                        response += f"- {key.capitalize()}: {value}\n"
                
                # ICD-10 codes
                if self.matched_icd10_codes:
                    response += "\nDIAGNOSIS CODES (ICD-10):\n"
                    for code in self.matched_icd10_codes:
                        response += f"- {code['code']} - {code['disease']}\n"
                
                # CPT-4 codes
                if self.matched_cpt4_codes:
                    response += "\nPROCEDURE CODES (CPT-4):\n"
                    for code in self.matched_cpt4_codes:
                        response += f"- {code['code']} - {code['procedure']}\n"
                
                response += "\nWould you like to add any additional information to the claim? For example:\n- Service date\n- Place of service\n- Referring provider\n- NPI number\n- Additional insurance information"
                
                self.add_to_history("assistant", response)
                print("Assistant:", response)
                
            except Exception as e:
                print(f"Error processing code selections: {e}")
                response = "I'm having trouble understanding your code selections. Please use the format '1a, 2b' for diagnoses and procedures. For example, '1a, 2c' means you want the first code (a) for diagnosis 1 and the third code (c) for diagnosis 2."
                self.add_to_history("assistant", response)
                print("Assistant:", response)
    
    def review_claim(self, user_input):
        """Handle the user's request to add more information or finalize the claim"""
        finalize_phrases = [
            "no", "done", "complete", "finished", "that's all", "finalize", "finalise", "good job", "looks good", "all set", "perfect", "submit", "ok", "okay", "go ahead", "ready", "proceed", "confirm", "yes", "save"
        ]
        if any(phrase in user_input.lower() for phrase in finalize_phrases):
            # User is done, finalize the claim
            filename = self.generate_cms1500_pdf()  # Regenerate with any final updates
            response = f"Your claim has been finalized and saved as '{filename}'. You can download this PDF file for submission."
            self.add_to_history("assistant", response)
            print("Assistant:", response)

            # Present the user with the next action menu
            menu = (
                "What would you like to do next?\n"
                "1. Start a new patient case\n"
                "2. Add or modify diagnoses or procedures\n"
                "3. Look up ICD-10 or CPT-4 code meanings\n"
                "4. Learn about medical coding"
            )
            self.add_to_history("assistant", menu)
            print("Assistant:", menu)
            self.current_state = "post_claim_menu"
        else:
            # User wants to add more information
            system_prompt = """
            The user is providing additional information for the medical claim. Extract any relevant information such as:
            - Service date
            - Place of service
            - Referring provider
            - NPI number
            - Additional insurance info
            - Other relevant claim details
            
            Format your response as JSON with relevant keys and values.
            """
            
            response = self.generate_llm_response(system_prompt)
            
            # Try to extract JSON from the response
            try:
                # Find JSON in the response
                json_pattern = r'\{.*\}'
                json_match = re.search(json_pattern, response, re.DOTALL)
                
                if json_match:
                    json_str = json_match.group(0)
                    additional_info = json.loads(json_str)
                    
                    # Update patient info with additional data
                    for key, value in additional_info.items():
                        if value not in [None, "", "null"]:
                            self.patient_info[key] = value
                
                # Regenerate the claim form with the updated information
                filename = self.generate_cms1500_pdf()
                
                response = f"I've updated the claim form with the additional information and saved it as '{filename}'. Would you like to add any other details, or shall we finalize the claim?"
                self.add_to_history("assistant", response)
                print("Assistant:", response)
                
            except Exception as e:
                print(f"Error processing additional information: {e}")
                response = "I've noted your additional information. Is there anything else you'd like to add before we finalize the claim?"
                self.add_to_history("assistant", response)
                print("Assistant:", response)
    
    def collect_summary(self, user_input):
        """Process all information provided in summary mode"""
        # Extract patient information
        patient_info_prompt = """
        Extract patient information from the text. Look for:
        - Full name
        - Date of birth
        - Gender
        - Address (optional)
        - Phone number (optional)
        - Insurance provider
        - Insurance ID/Policy number
        - Group number (optional)
        
        Format your response as JSON with keys: name, dob, gender, address, phone, insurance, policy, group.
        For any missing information, use null or empty string.
        """
        
        patient_info_response = self.generate_llm_response(patient_info_prompt)
        
        try:
            # Find JSON in the response
            json_pattern = r'\{.*\}'
            json_match = re.search(json_pattern, patient_info_response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                extracted_info = json.loads(json_str)
                
                # Update patient info with extracted data
                for key, value in extracted_info.items():
                    if value not in [None, "", "null"]:
                        self.patient_info[key] = value
        except Exception as e:
            print(f"Error parsing patient info: {e}")
        
        # Extract diagnoses and procedures
        self.collect_clinical_notes(user_input)
        
        # Generate the claim form
        filename = self.generate_cms1500_pdf()
        
        response = f"I've processed all the information and generated a claim form saved as '{filename}'. Would you like to review the claim details or make any adjustments?"
        self.add_to_history("assistant", response)
        print("Assistant:", response)
        
        self.current_state = "reviewing_claim"

    def generate_cms1500_pdf(self):
        """Generate a CMS-1500 claim form as PDF with dynamic layout."""
        patient_name = self.patient_info.get('name', 'Unknown').replace(' ', '_')
        filename = f"claim_{patient_name}.pdf"

        # Update the filename in the PDFBuilder instance
        self.pdf_builder.filename = filename

        # Title
        self.pdf_builder.canvas.setFont("Helvetica-Bold", 16)
        self.pdf_builder.canvas.setFillColor(colors.black)
        title = "CMS-1500 HEALTH INSURANCE CLAIM FORM EXAMPLE"
        title_width = self.pdf_builder.canvas.stringWidth(title, "Helvetica-Bold", 16)
        self.pdf_builder.canvas.drawString((self.pdf_builder.width - title_width) / 2, self.pdf_builder.y_position, title)
        self.pdf_builder.y_position -= 0.5 * inch

        # Patient Info
        self.pdf_builder.draw_section_header("PATIENT INFORMATION")
        patient_data = [
            ["Name:", self.patient_info.get('name', 'N/A')],
            ["DOB:", self.patient_info.get('dob', 'N/A')],
            ["Gender:", self.patient_info.get('gender', 'N/A')],
            ["Address:", self.patient_info.get('address', 'N/A')],
            ["Phone:", self.patient_info.get('phone', 'N/A')]
        ]
        self.pdf_builder.draw_table(patient_data, col_widths=[1.5 * inch, 4.5 * inch])

        # Insurance Info
        self.pdf_builder.draw_section_header("INSURANCE INFORMATION")
        insurance_data = [
            ["Provider:", self.patient_info.get('insurance', 'N/A')],
            ["Policy #:", self.patient_info.get('policy', 'N/A')],
            ["Group #:", self.patient_info.get('group', 'N/A')]
        ]
        self.pdf_builder.draw_table(insurance_data, col_widths=[1.5 * inch, 4.5 * inch])

        # Clinical Info
        if hasattr(self, 'clinical_info') and self.clinical_info:
            self.pdf_builder.draw_section_header("CLINICAL INFORMATION")
            clinical_data = [[f"{key.replace('_', ' ').capitalize()}:", str(value)] for key, value in self.clinical_info.items()]
            self.pdf_builder.draw_table(clinical_data, col_widths=[1.5 * inch, 4.5 * inch])

        # Diagnoses
        if self.matched_icd10_codes:
            self.pdf_builder.draw_section_header("DIAGNOSIS CODES (ICD-10)")
            diagnosis_data = [["Code", "Description"]] + [[code['code'], code['disease']] for code in self.matched_icd10_codes]
            self.pdf_builder.draw_table(diagnosis_data, col_widths=[1.5 * inch, 4.5 * inch])

        # Procedures
        if self.matched_cpt4_codes:
            self.pdf_builder.draw_section_header("PROCEDURE CODES (CPT-4)")
            procedure_data = [["Code", "Description"]] + [[code['code'], code['procedure']] for code in self.matched_cpt4_codes]
            self.pdf_builder.draw_table(procedure_data, col_widths=[1.5 * inch, 4.5 * inch])

        # Footer
        self.pdf_builder.add_footer()

        # Save the PDF
        self.pdf_builder.save()
        return filename
    
    def handle_default_conversation(self, user_input):
        """Handle generic conversation using GPT"""
        if self.current_state == "greeting":
            if user_input.strip() in ["1", "guided", "step by step"]:
                self.current_state = "collecting_patient_info"
                prompt = "First, I need the essential patient information:\n- Full name\n- Date of birth\n- Gender\n- Insurance provider\n- Insurance ID/policy number\n\nPlease provide as many of these details as you have available."
                self.add_to_history("assistant", prompt)
                print("Assistant:", prompt)
            elif user_input.strip() in ["2", "summary", "all at once"]:
                self.summary_mode = True
                self.current_state = "collecting_summary"
                prompt = "Please provide all the information at once, including:\n1. Patient Information (name, DOB, gender, insurance details)\n2. Clinical Notes (diagnoses and procedures)\n3. Any additional information (service dates, place of service, etc.)"
                self.add_to_history("assistant", prompt)
                print("Assistant:", prompt)
            elif user_input.strip() in ["3", "upload", "document", "pdf", "jpg", "jpeg"]:
                self.current_state = "processing_document"
                prompt = "Please provide the path to your PDF or JPG document. I'll extract the information and ask for any missing essential details."
                self.add_to_history("assistant", prompt)
                print("Assistant:", prompt)
            else:
                response = "Please choose either option 1 (guided mode), 2 (summary mode), or 3 (upload document)."
                self.add_to_history("assistant", response)
                print("Assistant:", response)
        else:
            system_prompt = """
            You are an AI medical coding assistant that helps healthcare providers accurately code diagnoses with ICD-10 codes, procedures with CPT-4 codes, and generate insurance claim forms.
            
            Based on the conversation history, determine what the user needs help with:
            1. Starting a new patient case
            2. Adding or modifying diagnoses or procedures
            3. Reviewing ICD-10 or CPT-4 codes
            4. Generating a claim form
            5. Learning about medical coding
            6. Something else (provide helpful information)
            
            Respond appropriately and suggest the next best action.
            """
            
            self.generate_llm_response(system_prompt)

    def handle_post_claim_menu(self, user_input):
        """Handle the menu after claim finalization"""
        # Map user input to actions
        choice = user_input.strip().lower()
        if choice in ["1", "start", "new patient", "new case"]:
            self.patient_info = {}
            self.diagnoses = []
            self.procedures = []
            self.matched_icd10_codes = []
            self.matched_cpt4_codes = []
            self.current_state = "collecting_patient_info"
            prompt = "Let's start a new patient case. Please provide the essential patient information: Full name, Date of birth, Gender, Insurance provider, Insurance ID/policy number."
            self.add_to_history("assistant", prompt)
            print("Assistant:", prompt)
        elif choice in ["2", "add", "modify", "diagnoses", "procedures"]:
            self.current_state = "collecting_clinical_notes"
            prompt = "Please provide the updated diagnoses or procedures."
            self.add_to_history("assistant", prompt)
            print("Assistant:", prompt)
        elif choice in ["3", "review", "lookup", "look up", "codes", "icd-10", "cpt-4", "meaning", "meanings"]:
            self.current_state = "code_lookup"
            prompt = "Please enter the ICD-10 or CPT-4 code(s) you want to look up (separated by commas if multiple)."
            self.add_to_history("assistant", prompt)
            print("Assistant:", prompt)
        elif choice in ["4", "learn", "about", "medical coding"]:
            self.current_state = "learning"
            prompt = "What would you like to learn about medical coding? (ICD-10, CPT-4, claim forms, etc.)"
            self.add_to_history("assistant", prompt)
            print("Assistant:", prompt)
        else:
            prompt = "Please choose a valid option from the menu (1-4)."
            self.add_to_history("assistant", prompt)
            print("Assistant:", prompt)

    def code_lookup(self, user_input):
        """Look up ICD-10 or CPT-4 code meanings and helpful info"""
        codes = [code.strip().upper() for code in user_input.split(",") if code.strip()]
        results = []
        for code in codes:
            found = False
            for entry in self.icd10_data:
                if entry["code"].upper() == code:
                    # Clean, professional output
                    results.append(f"ICD-10 {code}: {entry['disease']}\n  Category: {entry['category']}")
                    found = True
                    break
            if not found:
                for entry in self.cpt4_data:
                    if entry["code"].upper() == code:
                        results.append(f"CPT-4 {code}: {entry['procedure']}")
                        found = True
                        break
            if not found:
                results.append(f"Code {code} not found in ICD-10 or CPT-4 database.")
        response = "\n\n".join(results)
        self.add_to_history("assistant", response)
        print("Assistant:", response)
        # After lookup, return to the post-claim menu
        menu = (
            "What would you like to do next?\n"
            "1. Start a new patient case\n"
            "2. Add or modify diagnoses or procedures\n"
            "3. Look up ICD-10 or CPT-4 code meanings\n"
            "4. Learn about medical coding"
        )
        self.add_to_history("assistant", menu)
        print("Assistant:", menu)
        self.current_state = "post_claim_menu"

    def process_document(self, file_path):
        """Process PDF or JPG document to extract text"""
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                return "Error: File not found. Please provide a valid file path."

            # Get file extension
            _, ext = os.path.splitext(file_path.lower())
            
            # Process based on file type
            if ext == '.pdf':
                try:
                    # Convert PDF to images with Poppler path
                    images = convert_from_path(file_path, poppler_path=self.poppler_path)
                    text = ""
                    for image in images:
                        # Extract text from each page
                        text += pytesseract.image_to_string(image) + "\n"
                except Exception as e:
                    return f"Error processing PDF: {str(e)}. Please ensure Poppler is installed and the path is correct."
            elif ext in ['.jpg', '.jpeg', '.png']:
                # Process image directly
                image = Image.open(file_path)
                text = pytesseract.image_to_string(image)
            else:
                return "Error: Unsupported file format. Please provide a PDF or JPG/JPEG/PNG file."

            # Extract information using GPT
            system_prompt = """
            Extract patient information and medical details from the provided text. Look for:
            1. Patient Information:
               - Full name
               - Date of birth
               - Gender
               - Insurance provider
               - Insurance ID/policy number
               - Group number (optional)
            2. Clinical Information:
               - Diagnoses
               - Procedures
               - Service dates
               - Place of service
               - Provider information
            
            Format your response as JSON with two main sections: patient_info and clinical_info.
            """
            
            # Add the extracted text to the conversation
            self.add_to_history("system", f"Extracted text from document:\n{text}")
            
            # Get structured information using GPT
            response = self.generate_llm_response(system_prompt)
            
            try:
                # Find JSON in the response
                json_pattern = r'\{.*\}'
                json_match = re.search(json_pattern, response, re.DOTALL)
                
                if json_match:
                    json_str = json_match.group(0)
                    extracted_info = json.loads(json_str)
                    
                    # Update patient info
                    if 'patient_info' in extracted_info:
                        # Map alternative keys to standard keys
                        key_map = {
                            'full_name': 'name',
                            'date_of_birth': 'dob',
                            'insurance_provider': 'insurance',
                            'insurance_id': 'policy'
                        }
                        for key, value in extracted_info['patient_info'].items():
                            std_key = key_map.get(key, key)
                            if value not in [None, "", "null"]:
                                self.patient_info[std_key] = value
                    
                    # Process clinical information
                    if 'clinical_info' in extracted_info:
                        clinical_info = extracted_info['clinical_info']
                        # Extract diagnoses and procedures
                        if 'diagnoses' in clinical_info:
                            self.diagnoses = clinical_info['diagnoses']
                        if 'procedures' in clinical_info:
                            self.procedures = clinical_info['procedures']
                        # Store other clinical info separately
                        self.clinical_info = {k: v for k, v in clinical_info.items() if k not in ['diagnoses', 'procedures'] and v not in [None, "", "null"]}
                    else:
                        self.clinical_info = {}
                    
                    # Check for missing essential information
                    missing_fields = []
                    for field, description in self.essential_info_fields.items():
                        if field not in self.patient_info or not self.patient_info[field]:
                            missing_fields.append(description)
                    
                    if missing_fields:
                        # Ask for missing information
                        fields_str = ", ".join(missing_fields)
                        response = f"I've extracted information from your document, but I still need the following essential details: {fields_str}. Please provide these missing pieces of information."
                        self.current_state = "collecting_patient_info"
                        self.add_to_history("assistant", response)
                        print("Assistant:", response)
                        return response
                    else:
                        # Move to processing diagnoses and procedures
                        response = "I've extracted the information from your document. Now, I'll process the diagnoses and procedures to find the appropriate codes."
                        self.current_state = "collecting_clinical_notes"
                        self.add_to_history("assistant", response)
                        print("Assistant:", response)
                        return response
                
            except Exception as e:
                print(f"Error processing extracted information: {e}")
                return "I had trouble processing the information from your document. Please provide the information manually or try with a different document."
            
        except Exception as e:
            print(f"Error processing document: {e}")
            return f"Error processing document: {str(e)}"
