from config import CATEGORY_GUIDE


class ClassificationRules:
    @staticmethod
    def get_prompt():
        category_desc = "\n".join([f"{k}. {v}" for k, v in CATEGORY_GUIDE.items()])

        return f"""
        [TASK 1: Classification]
        Classify based on these definitions:
        {category_desc}

        <Critical Rules>
        1. **Analyze Context**: Title has higher priority than Content.
        2. **Strict Mapping**: Map the content to the most appropriate Category ID.
        3. **Disambiguation (CRITICAL RULES)**:
            - **'Briefing/Session' Classification (Important)**: 
                - **Classify as 1 (Lecture)**: If it is about **School System, Major/Department(전공/학과), Field Practice(현장실습), Career Fair**, or General Job Briefing.
                - **Classify as 4 (Activity)**: ONLY if the briefing is specifically for a **Bootcamp, KDT(Digital Training), Supporters, or External Project Team**.
            - **'Fair' & 'Expo'**: Always **1 (Lecture)**.
            - **'Project' & 'Training'**: KDT, SSAFY, Jungle, Academy -> **4 (Activity)**.
            - **'Challenge' vs 'Competition'**: "Challenge/Contest" -> 2, "Hackathon/Competition" -> 3.
            - **Financial Aid**: -> **5 (Scholarship)**.
        """
