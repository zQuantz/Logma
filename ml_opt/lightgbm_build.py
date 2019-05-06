import pandas as pd
import numpy as np
import sys, os

from sklearn.model_selection import ParameterGrid
from sklearn.model_selection import StratifiedKFold

import lightgbm as lgbm
from sklearn.metrics import accuracy_score

import joblib
from joblib import delayed, Parallel

from datetime import datetime

def evalerror(labels, preds):
	preds[preds > 0.5] = 1
	preds[preds <= 0.5] = 0
	return 'accuracy', accuracy_score(preds, labels), True

dir_ = 'res'

def get_main_df():

	main = []

	for file in os.listdir('D:/AlgoMLData/Scaled/'):
		print(file)
		ticker = file.split('_')[0]
		df = pd.read_csv('D:/AlgoMLData/Scaled/{}'.format(file))
		df['Ticker'] = ticker
		main.append(df)

	main = pd.concat(main, axis=0).iloc[:, 1:].reset_index(drop=True)

	main.loc[main.TTC <= 20, 'TTC'] = 1
	main.loc[main.TTC > 20, 'TTC'] = 0

	main = main[(main.sig30 == 1) & (main.sig50 == 1)]

	print(main.TTC.sum() / main.shape[0])

	return main

def eval_fold(idct, idcv, X_train, y_train, param_grid, i):

	best_params = []

	xt, yt = X_train.values[idct, :], y_train[idct]
	xv, yv = X_train.values[idcv, :], y_train[idcv]
	
	for j, param in enumerate(ParameterGrid(param_grid)):
		
		gbm = lgbm.LGBMClassifier(objective='binary', **param)
		gbm = gbm.fit(xt, yt, eval_set=[(xv, yv)], eval_metric='auc',
					  early_stopping_rounds=10, verbose=250)

		key1 = list(gbm.best_score_)[0]
		best_params.append([param, gbm.best_score_[key1]['binary_logloss'], gbm.best_score_[key1]['auc']])

		print(j, '\n')

	with open('%s/results_%s.pkl' % (dir_,i), 'wb') as file:
		joblib.dump(best_params, file)

def go_parallel():

	main = get_main_df()

	train_pct = 0.5
	test_pct = 1 - train_pct
	validation_pct = 0.2

	idc = np.random.permutation(main.shape[0])
	train_len = int(train_pct * main.shape[0])

	print(main.shape)

	print(main.head())

	train = main.iloc[idc[:train_len], :]
	test = main.iloc[idc[train_len:], :]

	train_tickers = train.Ticker.values
	train_drawdowns = train.Drawdown.values
	train_directions = train.Direction.values
	y_train = train.TTC.values
	idx = train.columns.tolist().index('sig20')-1
	X_train = train.iloc[:, idx:-1]

	test_tickers = test.Ticker.values
	test_drawdown = test.Drawdown.values
	test_directions = test.Direction.values
	y_test = test.TTC.values
	idx = test.columns.tolist().index('sig20')-1
	X_test = test.iloc[:, idx:-1]

	## X-val
	idx = int(X_test.shape[0]*validation_pct)
	idc = np.random.permutation(X_test.shape[0])
	X_val = X_test.values[idc[:idx]]
	y_val = y_test[idc[:idx]]
	X_test = X_test.values[idc[idx:]]
	y_test = y_test[idc[idx:]]

	params = {
		'learning_rate': 0.05,
		'max_depth': 10,
		'min_child_weight': 0.0001,
		'n_estimators': 10000,
		'num_leaves': 19,
		'objective' : 'binary'
		}

	gbm = lgbm.LGBMClassifier(**params)
	gbm = gbm.fit(X_train, y_train, early_stopping_rounds=10, eval_set=[(X_val, y_val)], eval_metric='auc')

	## Check model accuracy
	y_pred = gbm.predict(X_test)
	print('Testing .. {} Trades .. Accuracy : {}'.format(X_train.shape[0], accuracy_score(y_pred, y_test)))

	## Save Model
	with open('models/lgbm_{}'.format(datetime.now().strftime('%Y-%m-%d')), 'wb') as file:
		joblib.dump(gbm, file)

	with open('models/lgbm_{}'.format(datetime.now().strftime('%Y-%m-%d')), 'rb') as file:
		gbm = joblib.load(file)

	## Check model accuracy
	y_pred = gbm.predict(X_test)
	print('Testing/Reloading .. {} Trades .. Accuracy : {}'.format(X_train.shape[0], accuracy_score(y_pred, y_test)))

if __name__ == '__main__':

	go_parallel()
