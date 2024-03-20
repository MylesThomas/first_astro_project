# my_first_dag.py

import os
# import time
# import datetime
import timeit
import pandas as pd
import numpy as np
import yfinance as yf
import json
# from pendulum import datetime # ... this was causing errors
# from datetime import timedelta
import datetime
from google.cloud import bigquery
# import os

from airflow.decorators import (
    dag,
    task,
)  # DAG and task decorators for interfacing with the TaskFlow API


@dag(
    schedule="@daily",
    # This DAG is set to run for the first time on March 9, 2023.
    start_date=datetime.datetime(2023, 3, 9), # add datetime. before, now that we don't use pendulum
    catchup=False, # good practice
    default_args={
        "retries": 2,  # If a task fails, it will retry 2 times, after 5 minutes each.
        "retry_delay": datetime.timedelta(minutes=5) # fixing import error timedelta(minutes=5)
    },
    tags=["example"],
)  # If set, this tag is shown in the DAG view of the Airflow UI
def my_first_dag():
    @task()
    def extract():
        """
        #### Extract task
        A simple "extract" task to get data ready for the rest of the pipeline.
        In this case, yfinance is our data source.
        """
        print(f"starting extract() ...")

        today = datetime.date.today() # datetime.date.today() 
        delta = datetime.timedelta(days=1) # datetime.timedelta(days=1)

        tix = ['BTC-USD', 'ETH-USD', 'SOL-USD']
        start = today - delta
        end = today

        data = yf.download(
            tickers=tix,
            period='1d',   # Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
            interval="1h", # Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
            start=start,
            end=end,
        )
        if 'Datetime' not in data.columns:
            raise Exception("There was an issue with the download from yfinance's API. Please try again.")
        
        print(f"finished extract().")
        return data

    @task(
        multiple_outputs=False
    )  # multiple_outputs=True unrolls dictionaries into separate XCom values
    def transform(data: pd.DataFrame): # input: pd.DataFrame
        """
        #### Transform task
        A simple "transform" task which takes in the collection of order data and
        cleans it up.
        """
        print(f"starting transform() ...")
        data = data['Adj Close']
        data.index = pd.to_datetime(data.index)
        data.reset_index(inplace=True)
        print(f"column names before melt/pivot: {data.columns}")
        data_melted = pd.melt(
            data,
            id_vars=['Datetime'], # id
            value_vars=['BTC-USD', 'ETH-USD', 'SOL-USD'], # values are in these 3 columns
            var_name='Ticker', # name of the category in value_vars
            value_name='Price' # what the tickers are measuring
        )
        print(f"column names after melt/pivot: {data_melted.columns}")
        print(data_melted)
        print(data_melted.dtypes)
        print(data_melted['Price'].sum())
        print(f"finished transform().")
        return data_melted

    @task()
    def load(data: pd.DataFrame): # input: pd.DataFrame
        """
        #### Load task
        A simple "load" task that takes in the result of the "transform" task and prints it out,
        instead of saving it to end user review
        """
        # add more dots since we are going further back now.....
        # os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../../key.json" #Service account key file path
        print(f"starting load() ...")
        
        # trying to figure out how file structure is once you deploy to Astro...
        SCRIPT_DIR = os.getcwd()
        print(f"script directory: {SCRIPT_DIR}")
        print(f"contents of script directory: {os.listdir(SCRIPT_DIR)}")
        
        PARENT_DIR = os.path.dirname(SCRIPT_DIR)
        print(f"parent directory: {PARENT_DIR}")
        print(f"contents of parent directory: {os.listdir(PARENT_DIR)}")

        INCLUDE_DIR = os.path.join(SCRIPT_DIR, "include")
        print(f"include directory: {INCLUDE_DIR}")
        print(f"contents of include directory: {os.listdir(INCLUDE_DIR)}")

        path_to_json_file = os.path.join(INCLUDE_DIR, "key.json")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path_to_json_file

        MY_PROJECT_ID = "turnkey-timer-416503"
        MY_DATASET_ID = "crypto_dataset_v1"
        MY_TABLE_ID = "popular_coins"
        table_id = f"{MY_PROJECT_ID}.{MY_DATASET_ID}.{MY_TABLE_ID}"

        os.environ["GCLOUD_PROJECT"] = MY_PROJECT_ID
        client = bigquery.Client()

        # print(f"Total order value is: {total_order_value:.2f}")
        schema = [
            # https://cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.schema.SchemaField
            bigquery.SchemaField(
                name="Datetime",
                field_type=bigquery.enums.SqlTypeNames.DATETIME,
                mode='REQUIRED'
            ),
            bigquery.SchemaField(
                name="Ticker",
                field_type=bigquery.enums.SqlTypeNames.STRING,
                mode='REQUIRED'
            ),
            bigquery.SchemaField(
                name="Price",
                field_type=bigquery.enums.SqlTypeNames.FLOAT64,
                mode='NULLABLE'
            ),
        ]

        # Create dataset/table, if it doesn't exist already
        try:
            dataset = client.create_dataset(MY_DATASET_ID)
            print(f"Created dataset {MY_DATASET_ID}")
        except:
            print(f"Dataset {MY_DATASET_ID} already exists")

        try:
            table_ref = client.dataset(MY_DATASET_ID).table(MY_TABLE_ID)
            table = bigquery.Table(table_ref, schema=schema)
            table = client.create_table(table)
            print(f"Created table {MY_TABLE_ID}")
        except:
            print(f"Table {MY_TABLE_ID} already exists")

        # Dump data from yfinance into table
        dataframe = data.copy()

        # https://cloud.google.com/bigquery/docs/samples/bigquery-load-table-dataframe
        job_config = bigquery.LoadJobConfig(
            # Specify a (partial) schema. All columns are always written to the
            # table. The schema is used to assist in data type definitions.
            
            schema=schema,
            
            # Optionally, set the write disposition. BigQuery appends loaded rows
            # to an existing table by default, but with WRITE_TRUNCATE write
            # disposition it replaces the table with the loaded data.
            
            # write_disposition="WRITE_TRUNCATE",
        )

        job = client.load_table_from_dataframe(
            dataframe,
            table_id,
            job_config=job_config
        )  # Make an API request.

        job.result()  # Wait for the job to complete.

        table = client.get_table(table_id)  # Make an API request.

        print(
            "Loaded {} rows and {} columns to {}".format(
                dataframe.shape[0], dataframe.shape[1], table_id
            )
        )

        print(
            "There are now {} rows and {} columns in {}".format(
                table.num_rows, len(table.schema), table_id
            )
        )

        # Add logic to run SQL queries

        # Perform a query.
        QUERY_CREATE_TABLE_PRICES_FROM_LAST_WEEK = (
            'CREATE OR REPLACE TABLE turnkey-timer-416503.crypto_dataset_v1.prices_from_past_week AS '
            f'SELECT Datetime, Ticker, Price FROM `{MY_PROJECT_ID}.{MY_DATASET_ID}.popular_coins` '
            'WHERE datetime <= CURRENT_DATETIME() '
            'AND DATETIME_ADD(Datetime, INTERVAL 24*7 HOUR) >= CURRENT_DATETIME()' # final '' has no whitespace
        )
        print(f"QUERY 1: {QUERY_CREATE_TABLE_PRICES_FROM_LAST_WEEK}")
        query_job = client.query(QUERY_CREATE_TABLE_PRICES_FROM_LAST_WEEK)  # API request
        rows = query_job.result()  # Waits for query to finish

        for row in rows:
            print(row.name)
            
        QUERY_CREATE_TABLE_CALCULATED_HOURLY_RETURNS = (
            'CREATE OR REPLACE TABLE turnkey-timer-416503.crypto_dataset_v1.calculated_hourly_returns AS '
            'SELECT Datetime, Ticker, Price, ((Price / lag(Price, 1) OVER (PARTITION BY Ticker ORDER BY Datetime)) - 1)* 100 AS hourly_return '
            f'FROM `{MY_PROJECT_ID}.{MY_DATASET_ID}.prices_from_past_week` '
            'Order by Ticker, Datetime'
        )
        print(f"QUERY 2: {QUERY_CREATE_TABLE_CALCULATED_HOURLY_RETURNS}")
        query_job = client.query(QUERY_CREATE_TABLE_CALCULATED_HOURLY_RETURNS)  # API request
        rows = query_job.result()  # Waits for query to finish

        QUERY_CREATE_TABLE_MAX_HOURLY_RETURNS = (
            'CREATE OR REPLACE TABLE turnkey-timer-416503.crypto_dataset_v1.max_hourly_returns AS '
            'SELECT Ticker, MAX(hourly_return) as max_return '
            'FROM `turnkey-timer-416503.crypto_dataset_v1.calculated_hourly_returns` '
            'GROUP BY Ticker '
            'ORDER BY max_return DESC;' # final '' has no whitespace
        )
        print(f"QUERY 3: {QUERY_CREATE_TABLE_MAX_HOURLY_RETURNS}")
        query_job = client.query(QUERY_CREATE_TABLE_MAX_HOURLY_RETURNS)  # API request
        rows = query_job.result()  # Waits for query to finish

        print(f"data is successfully loaded into Google BigQuery.")

        print(f"finished load().")


    # Tell the DAG what order to do the functions
    SCRIPT_DIR = os.getcwd()
    PARENT_DIR = os.path.dirname(SCRIPT_DIR)
    print(f"script directory: {SCRIPT_DIR}")
    start_of_script_time = (
        timeit.default_timer()
    )
    
    
    ticker_data = extract()
    ticker_data_clean = transform(ticker_data)
    load(ticker_data_clean)
    
    
    print("The Modeling Script has finished running.")
    print(
        f"Entire Script Runtime (Minutes): {(timeit.default_timer() - start_of_script_time) / 60:.2f}"
    )  # make sure to remove from final version of document


my_first_dag()