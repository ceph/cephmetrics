# Installation Process

## Objective:   
Run a Grafana instance to provide a monitoring dashboard to a ceph
cluster.

## Pre-requisites    
### Monitoring host  
- docker and docker-compose (for simplicity)  
- grafana image (official latest 4.3 release from docker hub)  
- graphite image (docker.io/abezhenar/graphite-centos7) 
- clone the cephmetrics repo (docker configuration, dashboards)
- host that will run the monitor should have passwordless ssh to all the ceph
nodes
- the storage for the graphite database should be on SSD/flash if possible
- needs PyYAML, tested with python 2.7.13

### Ceph Cluster Nodes
- collectd rpm (5.7 or above)

## Installation Sequence
Install the monitoring endpoint first, and then apply the collectd configuration
to each of the ceph nodes.  


## Setting Up the monitoring endpoint
On the monitoring host, perform the following steps;  
1. Pull the required docker images (*listed above*)   
2. we need to persist the grafana configuration db and settings, as well as the 
graphite data.  
```markdown
mkdir -p /opt/docker/grafana/etc
mkdir -p /opt/docker/grafana/data/plugins
mkdir -p /opt/docker/graphite
```
3. Download the additional status panel plugin
```markdown
cd /opt/docker/grafana/data/plugins
wget https://grafana.com/api/plugins/vonage-status-panel/versions/1.0.4/download
unzip download
rm -f download
```
4. Copy the seed .ini file for grafana to the containers etc directory, and reset
the permissions to be compatible with the containers
```markdown
cp etc/grafana/grafana.ini /opt/docker/grafana/etc
chown -R 104:107 /opt/docker/grafana
chown -R 997 /opt/docker/graphite
chmod g+w /opt/docker/graphite

```
5. Edit the docker-compose.yml example (if necessary)
6. From the directory with the compose file, issue  
```
docker-compose up -d
```
7. check that the containers are running and the endpoints are listening  
7.1 Use ```docker ps```  
7.2 use ```netstat``` and look for the following ports: 3000,80,2003,2004,7002  
7.3 open a browser and connect to graphite - it should be running on port 80 of
the local machine
8. Add the graphite instance as a datasource to grafana  
8.1 update setup/add_datasource.json with the IP of the host machine  
8.2 register the graphite instance to grafana as the default data source  
```markdown
curl -u admin:admin -H "Content-Type: application/json" -X POST http://localhost:3000/api/datasources \
--data-binary @setup/add_datasource.json
```
9. the sample dashboards need to be added/edited to reflect the ceph cluster to
monitor  
9.1 seed dashboards are provided in the dashboards/current directory   
9.2 edit ```dashboard.yml``` with the shortnames of the OSD's and RGW's, plus
the dns domain name of the environment.  
9.3 run the following command  
```markdown
python dashUpdater.py
```
  
  
### Updating the dashboards
After adding ceph nodes to the configuration, update the ```dashboard.yml``` 
file, and then rerun the ```dashUpdater.py``` script.


## Configuration on Each Ceph Node
1. install collectd (this will also require libcollectdclient)
2. create the required directories for the cephmetrics collectors (see known
issues [2])
```markdown
mkdir -p /usr/lib64/collectd/python-plugins/collectors
```
3. copy the collectors to the directory created in [2], and cephmetrics.py
to /usr/lib64/collectd/python-plugins
4. Setup the collectd plugins  
4.1 Update the write_graphite.conf file to specify the hostname where the 
grafana/graphite environment is (use a hostname not IP - anecdotally I found that
with an IP the plugin fails to connect to the graphite container port?)    
4.2 copy the example plugin files to the /etc/collectd.d directory (i.e. cpu.conf,
memory.conf etc)  
5. update the "ClusterName" parameter in the cephmetrics plugin file to match
 the name of your ceph cluster (default is 'ceph')
6. copy the example collectd.conf file to the ceph node (or update the existing
configuration to ensure there is a ```Include "/etc/collectd.d/*.conf"``` entry)
7. enable collectd
8. start collectd
9. check collectd is running without errors

## Known Issues
1. Following a reboot of an OSD node, the cephmetrics collectd plugin doesn't send disk 
stats. ***Workaround**: Following the reboot of an OSD, restart the collectd service.*  
2. the cephmetrics.py and collectors should be installed through python-setuptools to cut down on 
the installation steps.  
3. At-A-Glance Health History chart doesn't work as hoped due to interpolation over the
7 day timeline. For example a 4 gets averaged over a number of samples to fit on
the graph and appears as a '1'!  
4. you can't easily export from the UI and then import programmitically with curl.
The export process puts additional metadata into the json, that is used by the 
import UI - but this makes the templates fail to initialise if you try to use the 
same file from a curl request.  
5. The "at a glance" dashboard has some singlestat panels for host counts of OSD's
and RGW's. These values can be wrong - the query needs some work!  




