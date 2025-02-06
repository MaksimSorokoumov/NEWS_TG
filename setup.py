from setuptools import setup, find_packages

setup(
    name="telegram-ai-assistant",
    version="0.1.0",
    description="ИИ-ассистент для анализа переписки в Telegram и интеграций с внешними источниками",
    author="Ваше имя",
    author_email="your.email@example.com",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=[
        "requests",
        "pandas",
        "numpy",
        "scikit-learn",
        "nltk",
        "spacy",
        "transformers",
        "torch",
        "tensorflow",
        "kafka-python",
        "pika"
    ],
    entry_points={
        "console_scripts": [
            "run_assistant=main:main",
        ],
    },
)

