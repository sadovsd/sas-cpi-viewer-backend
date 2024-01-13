# CPI Viewer Backend
A data visualization backend that uses saspy python module inside of flask to connect to SAS OnDemand server and retrieve data from CPI government files.

## 1. Set up free SAS OnDemand account and configure things
- https://welcome.oda.sas.com
- In SAS OnDemand, create a new directory cpi_viewer/data. Upload the files in cpi_data.zip to this directly. Also, create a new direcotry cpi_viewer/sas7bdat_data and upload the files from sas7bdat.zip into there.
- In SAS OnDemand, copy the specific path to the series file used in macro1.txt. For me, it is /home/u63731510/cpi_viewer/data/cu.series. Set this directly in the proc import of macro1.txt.
- Similarly in macro2.txt, replace the two paths with your own specific ones that include your SAS OnDemand account id.

## 2. Create the Docker image for the flask app
- in cpi-viewer-container file, add a .env file with your SAS OnDemand username and password. It should look like this:
OMRUSER=johndoe@gmail.com
OMRPW=password
- Within the cpi-viewer-container directory, execute the docker build command: docker build -t <docker_account_name>/<image_name>:1.1 .

## 3. Run and test the flask app locally
- To run the image locally, execute the docker run command: docker run -p 8000:8000 <docker_account_name>/<image_name>:1.1
- Test the first route with this sample call: http://localhost:8000/getAvailableSeries?1=SAF11211
- Test the second route with this sample call: http://localhost:8000/makeGraphReadyData?1=1938%2C2020%2CQuarterly%2Ccu.data.11.USFoodBeverage%2CCUUR0000SAF11211

## 4. Deploy the flask app to the Azure cloud (works on free account)
- Once you have the docker image built, upload it to your docker public registery with this command: docker push <docker_account_name>/<image_name>:1.1
- In Azure, create a new "Container App".
- For ingress options, set it to "enable ingress", ingress type = http, target port = 8000
- Set environmental variable NUM_WORKERS = 4. This value can be set higher, but this is a safe number. As a rule of thumb, the number of processes that can be spawned effeciently is 2*number of cores + 2.
- Set SAS_REQ_TIMEOUT = 5.
-  Set the 'Scale' setting to be between 1 and X instances so the container app dosen't shut down, if it is 0 it will power off in some time and will need a warmup start again.
- Bump up CPU to 1.0 and memory to 2.0 as the default is 0.5 and 1.0 for the Contaier app

