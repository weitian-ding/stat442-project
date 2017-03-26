
import csv
from random import shuffle

import numpy as np
from sklearn.model_selection import train_test_split
from quora_question_pairs_helpers import QuoraQuestionPairs

TRAIN_DATA = 'train.csv'

TRAIN_BALANCED = 'train_balanced.csv'
TEST = 'cv_test.csv'

LABEL_FILE = "labels.csv"

RATIO = 0.165

def main():
    pos_counter = 0
    total_counter = 0

    pos_rows = []
    neg_rows = []

    for row in QuoraQuestionPairs.training_set(TRAIN_DATA):
        total_counter += 1
        if row['is_duplicate'] == '1':
            pos_rows.append(row)
            pos_counter += 1
        else:
            neg_rows.append(row)

    balance_counter = int(pos_counter / RATIO - pos_counter)

    scale = balance_counter // len(neg_rows)

    neg_rows = (neg_rows * scale) + neg_rows[:(balance_counter % len(neg_rows))]

    balanced_data = pos_rows + neg_rows

    shuffle(balanced_data)

    #train, test = train_test_split(balanced_data, test_size=0.2, random_state=4242)


    with open(TRAIN_BALANCED, 'w') as csv_file:
        fieldnames = ["id", "qid1", "qid2", "question1", "question2", "is_duplicate"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        writer.writerows(balanced_data)

    labels = np.array([int(pair['is_duplicate']) for pair in QuoraQuestionPairs.training_set(TRAIN_BALANCED)], dtype=int)
    np.savetxt(LABEL_FILE, labels, delimiter=',', fmt='%s')


if __name__ == '__main__':
    main()
