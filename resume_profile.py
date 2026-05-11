import json
import re
from pathlib import Path

from resume_parser import ResumeParser


OUTPUT_PATH = Path("resume_profile.json")


KNOWN_SKILLS = [
    "python",
    "fastapi",
    "postgresql",
    "kafka",
    "pyspark",
    "databricks",
    "azure",
    "docker",
    "github actions",
    "linux",
    "sql",
    "redis",
    "spark",
    "git",
    "kubernetes",
    "react",
    "typescript",
]


TARGET_ROLES = [
    "backend engineer",
    "backend developer",
    "software engineer",
    "data engineer",
    "platform engineer",
]


class ResumeProfiler:
    def __init__(self):
        parser = ResumeParser()
        self.resume_text = parser.extract_text().lower()

    def extract_skills(self):
        found = []

        for skill in KNOWN_SKILLS:
            if skill in self.resume_text:
                found.append(skill)

        return sorted(list(set(found)))

    def extract_roles(self):
        found = []

        for role in TARGET_ROLES:
            if role in self.resume_text:
                found.append(role)

        return sorted(list(set(found)))

    def extract_experience(self):
        patterns = [
            r'(\d+)\+?\s+years',
            r'(\d+)\+?\s+year'
        ]

        for pattern in patterns:
            match = re.search(pattern, self.resume_text)

            if match:
                return f"{match.group(1)}+ years"

        return "Not specified"

    def build_profile(self):
        profile = {
            "primary_roles": self.extract_roles(),
            "skills": self.extract_skills(),
            "experience_level": self.extract_experience(),
            "preferred_domains": [
                "Backend Engineering",
                "Data Engineering",
                "Platform Engineering"
            ]
        }

        return profile

    def save_profile(self):
        profile = self.build_profile()

        with open(OUTPUT_PATH, "w") as f:
            json.dump(profile, f, indent=2)

        return profile


if __name__ == "__main__":
    profiler = ResumeProfiler()
    profile = profiler.save_profile()

    print(json.dumps(profile, indent=2))