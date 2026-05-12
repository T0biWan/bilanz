import logging

from config_loader import load_config
from label_data import apply_manual_labels, apply_labels, load_labels
from preprocess import preprocess_transactions
from create_bilanz import create_bilanz, write_bilanz

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    config = load_config("config/config.yaml")
    labels = load_labels("config/labels.yaml")

    preprocessed_df = preprocess_transactions(
        input_file=f"{config.paths.get('raw_dir')}/20260511-Export-Alle_Buchungen.xlsx",
        accounts=config.accounts,
        savings_accounts=config.savings_accounts,
    )
    preprocessed_df.to_excel(f"{config.paths.get('processed_dir')}/preprocessed.xlsx", index=False)

    auto_labeled_df = apply_labels(preprocessed_df, labels)
    labeled_df = apply_manual_labels(auto_labeled_df, "config/manual_labels.xlsx")
    labeled_df.to_excel(f"{config.paths.get('labeled_dir')}/labeled.xlsx", index=False)

    bilanz_df = create_bilanz(labeled_df)
    write_bilanz(bilanz_df, f"{config.paths.get('bilanz_dir')}/bilanz.xlsx")
