import datetime
import re

import numpy as np
import pandas as pd
from gensim.models import KeyedVectors
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.layers import Embedding, LSTM, Merge, Dropout, BatchNormalization, Dense, Conv1D, MaxPooling1D
from keras.models import Sequential
from keras.preprocessing import sequence
from keras.preprocessing.text import Tokenizer

TRAIN_DATA = 'input/train.csv'
TEST_DATA = 'input/test.csv'

TRAIN_PRED = 'data/lstm_train_pred.csv'
TEST_PRED = 'data/lstm_test_pred.csv'
SUBMISSION_FILE = 'data/lstm_test_pred_re_weighted.csv'

W2V_MODEL = 'models/GoogleNews-Vectors-negative300.bin'
MODEL_FILENAME = 'models/lstm-{0}'

W2V_DIM = 300
MAX_SEQ_LEN = 40
MAX_VOCAB_SIZE = 200000
LSTM_UNITS = 225
dense_units = 125
LSTM_DROPOUT = 0.25
dropout = 0.25
EPOCH = 30

POS_DISTRIB_IN_TEST = 0.1746

FEAT_TRAIN_FILE = 'features/train.csv'
FEAT_TEST_FILE = 'features/test.csv'

# cnn layer
cnn_nb_filters = 62
filter_length = 5
nb_filter = 64
pool_length = 4


def clean_txt(text):
    text = str(text).lower()

    re.sub(r"[^A-Za-z0-9^,!.\/'+-=]", ' ', text)  # removing non ASCII chars

    # Clean the text
    text = re.sub(r"[^A-Za-z0-9^,!.\/'+-=]", " ", text)
    text = re.sub(r"what's", "what is ", text)
    text = re.sub(r"\'s", " ", text)
    text = re.sub(r"\'ve", " have ", text)
    text = re.sub(r"can't", "cannot ", text)
    text = re.sub(r"n't", " not ", text)
    text = re.sub(r"i'm", "i am ", text)
    text = re.sub(r"\'re", " are ", text)
    text = re.sub(r"\'d", " would ", text)
    text = re.sub(r"\'ll", " will ", text)
    text = re.sub(r",", " ", text)
    text = re.sub(r"\.", " ", text)
    text = re.sub(r"!", " ! ", text)
    text = re.sub(r"\/", " ", text)
    text = re.sub(r"\^", " ^ ", text)
    text = re.sub(r"\+", " + ", text)
    text = re.sub(r"\-", " - ", text)
    text = re.sub(r"\=", " = ", text)
    text = re.sub(r"'", " ", text)
    text = re.sub(r"60k", " 60000 ", text)
    text = re.sub(r":", " : ", text)
    text = re.sub(r" e g ", " eg ", text)
    text = re.sub(r" b g ", " bg ", text)
    text = re.sub(r" u s ", " american ", text)
    text = re.sub(r'\0s', "0", text)
    text = re.sub(r" 9 11 ", "911", text)
    text = re.sub(r"e - mail", "email", text)
    text = re.sub(r"j k", "jk", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text


def texts_to_padded_seq(texts, tk):
    seq = tk.texts_to_sequences(texts)
    padded_seq = sequence.pad_sequences(seq, maxlen=MAX_SEQ_LEN)
    return padded_seq


def build_model(vocab_size, w2v_weights):
    model1 = Sequential()

    model1.add(Embedding(vocab_size,
                         W2V_DIM,
                         weights=[w2v_weights],
                         input_length=MAX_SEQ_LEN,
                         trainable=False))

    model1.add(Conv1D(62,
                      filter_length=5,
                      padding='valid',
                      activation='relu',
                      strides=1))

    model1.add(MaxPooling1D(pool_size=4))

    model1.add(Dropout(0.2))

    model1.add(LSTM(225,
                    dropout=0.25,
                    recurrent_dropout=0.25))
    return model1


def main():

    print('loading GoogleNews-Vectors-negative300.bin...')
    w2v_model = KeyedVectors.load_word2vec_format(W2V_MODEL, binary=True)

    # load data
    print('loading training data...')
    train_data = pd.read_csv(TRAIN_DATA).fillna('na')
    train_data.question1 = train_data.question1.map(clean_txt)
    train_data.question2 = train_data.question2.map(clean_txt)

    pos_distrib_in_train = train_data.is_duplicate.mean()
    print('{0}% positives in training data'.format(pos_distrib_in_train * 100))

    def re_weight(score):
        pa = POS_DISTRIB_IN_TEST / pos_distrib_in_train
        pb = (1 - POS_DISTRIB_IN_TEST) / (1 - pos_distrib_in_train)
        return pa * score / (pa * score + pb * (1 - score))

    print('loading testing data...')
    test_data = pd.read_csv(TEST_DATA).fillna('na')
    test_data.question1 = test_data.question1.map(clean_txt)
    test_data.question2 = test_data.question2.map(clean_txt)

    # tokenize
    print('tokenizing questions...')
    tk = Tokenizer(num_words=MAX_VOCAB_SIZE)
    print('sample')
    print(train_data.question1.head(1000))

    tk.fit_on_texts(train_data.question1.tolist()
                    + train_data.question2.tolist()
                    + test_data.question1.tolist()
                    + test_data.question2.tolist())
    print('{0} words'.format(len(tk.word_index)))

    seq1_train = texts_to_padded_seq(train_data.question1.tolist(), tk)
    seq2_train = texts_to_padded_seq(train_data.question2.tolist(), tk)
    y_train = np.array([train_data.is_duplicate]).T # column vector

    seq1_train_stacked = np.vstack((seq1_train, seq2_train))
    seq2_train_stacked = np.vstack((seq2_train, seq1_train))
    y_train_stacked = np.vstack((y_train, y_train))
    print('x1_dim={0} x2_dim={1} y_dim={2}'.format(seq1_train_stacked.shape, seq2_train_stacked.shape, y_train_stacked.shape))

    seq1_test = texts_to_padded_seq(test_data.question1.tolist(), tk)
    seq2_test = texts_to_padded_seq(test_data.question2.tolist(), tk)

    print('preparing w2v weight matrix...')
    vocab_size = len(tk.word_index) + 1
    w2v_weights = np.zeros((vocab_size, W2V_DIM))
    for word, i in tk.word_index.items():
        if word in w2v_model.vocab:
            w2v_weights[i] = w2v_model.word_vec(word)
    print('w2v weight matrix dim {0}'.format(w2v_weights.shape))

    '''
    # load features
    print('loading features...')
    feat_train = pd.read_csv(FEAT_TRAIN_FILE)
    print('features = {0}'.format(list(feat_train)))
    feat_train = feat_train.as_matrix()
    feat_train_stacked = np.vstack((feat_train, feat_train))
    feat_dim = feat_train.shape[1]
    feat_test = pd.read_csv(FEAT_TEST_FILE).as_matrix()
    '''

    # model
    print('building model...')

    '''
    feat_model = Sequential()
    feat_model.add(Dense(32, input_dim=feat_dim, activation='relu'))
    # feat_model.add(BatchNormalization())
    '''

    merged = Sequential()

    merged.add(Merge([build_model(vocab_size, w2v_weights), build_model(vocab_size, w2v_weights)], mode='concat'))
    merged.add(Dropout(dropout))
    merged.add(BatchNormalization())

    merged.add(Dense(dense_units, activation='relu'))
    merged.add(Dropout(dropout))
    merged.add(BatchNormalization())

    merged.add(Dense(dense_units, activation='relu'))
    merged.add(Dropout(dropout))
    merged.add(BatchNormalization())

    merged.add(Dense(1, activation='sigmoid'))

    merged.compile(loss='binary_crossentropy',
                   optimizer='adam',
                   metrics=['accuracy'])

    # train model
    print('training model...')

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')

    model_filename = MODEL_FILENAME.format(timestamp)

    early_stopping = EarlyStopping(monitor='val_loss', patience=3)
    model_checkpoint = ModelCheckpoint(model_filename,
                                       save_best_only=True,
                                       save_weights_only=True)

    hist = merged.fit([seq1_train_stacked, seq2_train_stacked],
                      y=y_train_stacked,
                      validation_split=0.2,
                      #class_weight=class_weight,
                      epochs=EPOCH,
                      batch_size=2048,
                      verbose=1,
                      shuffle=True,
                      callbacks=[early_stopping, model_checkpoint])

    merged.load_weights(model_filename)
    bst_val_score = min(hist.history['val_loss'])
    print('training finished')
    print('min cv log-loss {0}'.format(bst_val_score))

    # predict
    print('predicting testing set...')
    preds = merged.predict([seq1_test, seq2_test], batch_size=8192, verbose=1)
    preds += merged.predict([seq2_test, seq1_test], batch_size=8192, verbose=1)
    preds /= 2

    preds_test = pd.DataFrame({'test_id': range(0, test_data.shape[0]),
                               'is_duplicate': preds.ravel()})
    preds_test['is_duplicate'] = preds_test.is_duplicate.map(re_weight)
    print('prediction mean {0}'.format(preds_test.is_duplicate.mean()))

    print('writing predictions...')
    preds_test.to_csv(SUBMISSION_FILE, index=False)

    print('predicting training set...')
    preds = merged.predict([seq1_train, seq2_train], batch_size=8192, verbose=1)
    preds += merged.predict([seq2_train, seq1_train], batch_size=8192, verbose=1)
    preds /= 2

    preds_train = pd.DataFrame({'lstm_pred': preds.ravel()})

    print('writing predictions...')
    preds_train.to_csv(TRAIN_PRED, index=False)


if __name__ == '__main__':
    main()



