"""One-off maintenance helper: add reference translations (categories,
causes, organisation types, regions, document styles) to every catalogue.

Run after editing the reference lists in app/data.py. It refuses to overwrite
existing keys, so it is safe to re-run.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "data" / "i18n"

ADDITIONS: dict[str, dict[str, str]] = {
    "category.healthcare": {"en": "Healthcare", "fr": "Santé", "ar": "الرعاية الصحية"},
    "category.care": {"en": "Care work", "fr": "Aide à la personne", "ar": "أعمال الرعاية"},
    "category.education": {"en": "Education", "fr": "Éducation", "ar": "التعليم"},
    "category.hospitality": {"en": "Hospitality & tourism", "fr": "Hôtellerie et tourisme", "ar": "الضيافة والسياحة"},
    "category.construction": {"en": "Construction & trades", "fr": "Construction et métiers", "ar": "البناء والحرف"},
    "category.agriculture": {"en": "Agriculture & food", "fr": "Agriculture et alimentation", "ar": "الزراعة والأغذية"},
    "category.logistics": {"en": "Logistics & driving", "fr": "Logistique et conduite", "ar": "اللوجستيات والقيادة"},
    "category.manufacturing": {"en": "Manufacturing", "fr": "Industrie", "ar": "التصنيع"},
    "category.engineering": {"en": "Engineering", "fr": "Ingénierie", "ar": "الهندسة"},
    "category.it": {"en": "IT & software", "fr": "Informatique et logiciels", "ar": "تقنية المعلومات"},
    "category.finance": {"en": "Finance", "fr": "Finance", "ar": "المالية"},
    "category.legal": {"en": "Legal", "fr": "Juridique", "ar": "القانون"},
    "category.science": {"en": "Science & research", "fr": "Science et recherche", "ar": "العلوم والبحث"},
    "category.creative": {"en": "Creative & design", "fr": "Créatif et design", "ar": "الإبداع والتصميم"},
    "category.admin": {"en": "Administration", "fr": "Administration", "ar": "الإدارة"},
    "category.energy": {"en": "Energy", "fr": "Énergie", "ar": "الطاقة"},
    "category.sales": {"en": "Sales", "fr": "Ventes", "ar": "المبيعات"},
    "category.marketing": {"en": "Marketing", "fr": "Marketing", "ar": "التسويق"},
    "category.support": {"en": "Customer support", "fr": "Service client", "ar": "دعم العملاء"},
    "category.hr": {"en": "Human resources", "fr": "Ressources humaines", "ar": "الموارد البشرية"},
    "category.security": {"en": "Security", "fr": "Sécurité", "ar": "الأمن"},
    "category.public": {"en": "Public sector", "fr": "Secteur public", "ar": "القطاع العام"},
    "category.social": {"en": "Social work", "fr": "Travail social", "ar": "العمل الاجتماعي"},
    "category.automotive": {"en": "Automotive", "fr": "Automobile", "ar": "السيارات"},
    "category.aviation": {"en": "Aviation", "fr": "Aviation", "ar": "الطيران"},
    "category.retail": {"en": "Retail", "fr": "Commerce de détail", "ar": "التجزئة"},
    "category.other": {"en": "Other", "fr": "Autre", "ar": "أخرى"},
    "cause.education": {"en": "Education", "fr": "Éducation", "ar": "التعليم"},
    "cause.environment": {"en": "Environment", "fr": "Environnement", "ar": "البيئة"},
    "cause.health": {"en": "Health", "fr": "Santé", "ar": "الصحة"},
    "cause.humanitarian": {"en": "Humanitarian", "fr": "Humanitaire", "ar": "الإنساني"},
    "cause.animals": {"en": "Animals", "fr": "Animaux", "ar": "الحيوانات"},
    "cause.community": {"en": "Community", "fr": "Communauté", "ar": "المجتمع"},
    "cause.arts": {"en": "Arts & culture", "fr": "Arts et culture", "ar": "الفنون والثقافة"},
    "cause.sports": {"en": "Sports", "fr": "Sport", "ar": "الرياضة"},
    "cause.technology": {"en": "Technology", "fr": "Technologie", "ar": "التكنولوجيا"},
    "cause.other": {"en": "Other", "fr": "Autre", "ar": "أخرى"},
    "org.ngo": {"en": "NGO", "fr": "ONG", "ar": "منظمة غير حكومية"},
    "org.un": {"en": "UN agency", "fr": "Agence de l'ONU", "ar": "وكالة أممية"},
    "org.government": {"en": "Government", "fr": "Gouvernement", "ar": "حكومة"},
    "org.charity": {"en": "Charity", "fr": "Association caritative", "ar": "جمعية خيرية"},
    "org.school": {"en": "School", "fr": "École", "ar": "مدرسة"},
    "org.other": {"en": "Other", "fr": "Autre", "ar": "أخرى"},
    "region.eu": {"en": "European Union", "fr": "Union européenne", "ar": "الاتحاد الأوروبي"},
    "region.europe": {"en": "Europe", "fr": "Europe", "ar": "أوروبا"},
    "region.north_america": {"en": "North America", "fr": "Amérique du Nord", "ar": "أمريكا الشمالية"},
    "region.latam": {"en": "Latin America", "fr": "Amérique latine", "ar": "أمريكا اللاتينية"},
    "region.mena": {"en": "Middle East & North Africa", "fr": "Moyen-Orient et Afrique du Nord", "ar": "الشرق الأوسط وشمال أفريقيا"},
    "region.africa": {"en": "Africa", "fr": "Afrique", "ar": "أفريقيا"},
    "region.asia_pacific": {"en": "Asia-Pacific", "fr": "Asie-Pacifique", "ar": "آسيا والمحيط الهادئ"},
    "region.worldwide": {"en": "Worldwide", "fr": "Monde entier", "ar": "العالم"},
    "docgen.style_international": {"en": "International", "fr": "International", "ar": "دولي"},
    "docgen.style_us": {"en": "United States", "fr": "États-Unis", "ar": "الولايات المتحدة"},
    "docgen.style_uk": {"en": "United Kingdom", "fr": "Royaume-Uni", "ar": "المملكة المتحدة"},
    "docgen.style_de": {"en": "Germany", "fr": "Allemagne", "ar": "ألمانيا"},
    "docgen.style_fr": {"en": "France", "fr": "France", "ar": "فرنسا"},
    "docgen.style_ar": {"en": "Arabic-speaking countries", "fr": "Pays arabophones", "ar": "الدول الناطقة بالعربية"},
}


def main() -> None:
    for lang in ("en", "fr", "ar"):
        path = I18N / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        added = 0
        for key, values in ADDITIONS.items():
            if key not in data:
                data[key] = values[lang]
                added += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{lang}: +{added} keys")


if __name__ == "__main__":
    main()
