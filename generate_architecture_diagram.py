import os
os.environ["PATH"] += os.pathsep + r"C:\Program Files\Graphviz\bin"

from diagrams import Cluster, Diagram, Edge
from diagrams.onprem.compute import Server
from diagrams.onprem.database import MySQL as MariaDB # Use MySQL icon for MariaDB
from diagrams.onprem.network import Internet
from diagrams.onprem.queue import Kafka
from diagrams.programming.language import Python, Javascript
from diagrams.generic.device import Tablet
from diagrams.aws.storage import S3 as Minio # Use S3 icon for MinIO (compatible)

with Diagram("IoT Realtime Dashboard Architecture", show=False, filename="iot_system_architecture", direction="LR"):
    
    with Cluster("Data Source"):
        sensors = Tablet("Sensors (ESP32/Arduino)")
        
    with Cluster("Ingestion Layer"):
        ingestion = Python("Ingestion Service")
    
    with Cluster("Docker Infrastructure"):
        with Cluster("Message Broker"):
            kafka = Kafka("Kafka Broker")
            zookeeper = Server("Zookeeper")
            zookeeper - Edge(style="dashed") - kafka
            
        with Cluster("Storage"):
            mariadb = MariaDB("MariaDB (SQL)")
            minio = Minio("MinIO (Object)")
            
        with Cluster("Processing Workers"):
            ai_worker = Python("AI Worker")
            db_worker = Python("Database Worker")
            storage_worker = Python("Storage Worker")
            mqtt_bridge = Python("MQTT Bridge")
            
        with Cluster("Application"):
            api_server = Python("API Server")
            hivemq = Server("HiveMQ Broker")
            transcript_builder = Python("Transcript Builder")
            filecoin_uploader = Python("Filecoin Uploader")

    with Cluster("User Interface"):
        dashboard = Javascript("Web Dashboard")
        
    with Cluster("Decentralized Storage"):
        filecoin = Internet("Filecoin Network")
        ipfs = Internet("IPFS")

    # Data Flow
    sensors >> Edge(label="Serial/UART") >> ingestion
    ingestion >> Edge(label="JSON + RSSI") >> kafka
    
    # Kafka Consumers
    kafka >> Edge(label="raw_sensor_data") >> ai_worker
    kafka >> Edge(label="raw_sensor_data") >> db_worker
    kafka >> Edge(label="raw_sensor_data") >> storage_worker
    kafka >> Edge(label="raw_sensor_data") >> mqtt_bridge
    
    # AI Feedback
    ai_worker >> Edge(label="ai_predictions") >> kafka
    
    # Storage
    db_worker >> mariadb
    storage_worker >> minio
    
    # Application Layer
    mariadb >> api_server
    minio >> api_server
    mqtt_bridge >> hivemq
    hivemq >> Edge(label="WebSocket") >> dashboard
    
    # Decentralized Storage Flow
    mariadb >> transcript_builder
    transcript_builder >> filecoin_uploader
    filecoin_uploader >> filecoin
    filecoin_uploader >> ipfs
