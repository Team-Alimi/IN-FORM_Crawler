class DateExtractionRules:
    @staticmethod
    def get_prompt(current_date):
        return f"""
        [TASK 2: Date Extraction]
        Extract 'start_date' and 'due_date' based on the Reference Date: {current_date}.
        
        <Definition>
        1. **start_date**: The day the actual event/program/activity **BEGINS**.
        2. **due_date**: The day the actual event/program/activity **ENDS**.
        
        <Extraction Logic>
        - **Target**: Event Period (Ignore Application Period).
        - **Range**: "Dec 1 ~ Dec 3" -> start=Dec 1, due=Dec 3. (One-day event: start=due).
        
        <Advanced Reasoning (CRITICAL)>
        You must infer dates from relative or ambiguous terms using the Reference Date ({current_date}):
        1. **Relative Terms**: "Next Friday", "End of this month", "Tomorrow", "In 2 weeks" -> Calculate the exact YYYY-MM-DD.
        2. **Holidays/Named Days**: "Christmas", "Chuseok", "New Year" -> Convert to the specific date of that year.
        3. **Vague Expressions**: 
           - "After the weekend" -> The following Monday.
           - "Midnight" -> The date represented by that night.
        4. **Unknowable**: If the text says "After construction ends" or "TBD" (no specific time clue), return null.
        
        - **Format**: YYYY-MM-DD (ISO 8601).
        """