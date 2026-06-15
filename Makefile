.PHONY: setup demo dashboard run resolve clean

setup:
	pip install -r requirements.txt

demo:
	python dashboard.py --demo

dashboard:
	python dashboard.py

run:
	python monitor.py

resolve:
	python resolver.py --force

clean:
	rm -rf data state output __pycache__
