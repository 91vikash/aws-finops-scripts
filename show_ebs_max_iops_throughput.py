import boto3
import datetime

# Configuration: AWS profile and region
AWS_PROFILE = "profile_name"
REGION = "region_name"

# Initialize AWS session with specified profile and region
session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)

# Initialize AWS clients
ec2_client = session.client("ec2", region_name=REGION)
cloudwatch_client = session.client("cloudwatch", region_name=REGION)

def get_instance_details(instance_id, ec2_client):
    """
    Retrieve instance details such as instance type, name, and status from EC2.
    """
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        reservations = response.get('Reservations', [])
        if reservations and reservations[0].get('Instances'):
            instance = reservations[0]['Instances'][0]
            instance_type = instance.get('InstanceType', '')
            instancename, status_tag = '', ''
            for tag in instance.get('Tags', []):
                if tag['Key'].lower() == 'name':
                    instancename = tag['Value']
                if tag['Key'].lower() == 'status':
                    status_tag = tag['Value']
            return instance_type, instancename, status_tag
    except Exception as e:
        print(f"Error retrieving details for instance {instance_id}: {e}")
    return '', '', ''

def get_max_iops(volume_id, cloudwatch_client, start_time, end_time):
    """
    Retrieve maximum IOPS (ReadOps + WriteOps) for a given EBS volume within a specified time range.
    """
    try:
        response = cloudwatch_client.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'readOps',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/EBS',
                            'MetricName': 'VolumeReadOps',
                            'Dimensions': [{'Name': 'VolumeId', 'Value': volume_id}]
                        },
                        'Period': 300,  # 5-minute intervals
                        'Stat': 'Sum'
                    }
                },
                {
                    'Id': 'writeOps',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/EBS',
                            'MetricName': 'VolumeWriteOps',
                            'Dimensions': [{'Name': 'VolumeId', 'Value': volume_id}]
                        },
                        'Period': 300,
                        'Stat': 'Sum'
                    }
                }
            ],
            StartTime=start_time,
            EndTime=end_time
        )
        
        # Extract metric values
        read_ops_values, write_ops_values, timestamps = [], [], []
        for result in response.get('MetricDataResults', []):
            if result.get('Id') == 'readOps':
                read_ops_values = result.get('Values', [])
                timestamps = result.get('Timestamps', [])
            elif result.get('Id') == 'writeOps':
                write_ops_values = result.get('Values', [])
        
        # Compute max IOPS
        max_iops, max_iops_timestamp = 0, None
        if len(read_ops_values) == len(write_ops_values) == len(timestamps):
            for i in range(len(read_ops_values)):
                current_iops = (read_ops_values[i] + write_ops_values[i]) / 300
                if current_iops > max_iops:
                    max_iops = current_iops
                    max_iops_timestamp = timestamps[i]
        
        return max_iops, max(read_ops_values, default=0), max(write_ops_values, default=0), max_iops_timestamp
    except Exception as e:
        print(f"Error retrieving CloudWatch metrics for volume {volume_id}: {e}")
        return 0, 0, 0, None

def get_max_throughput(volume_id, cloudwatch_client, start_time, end_time):
    """
    Retrieve maximum throughput (ReadBytes + WriteBytes) for a given EBS volume within a specified time range.
    """
    try:
        response = cloudwatch_client.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'readBytes',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/EBS',
                            'MetricName': 'VolumeReadBytes',
                            'Dimensions': [{'Name': 'VolumeId', 'Value': volume_id}]
                        },
                        'Period': 300,
                        'Stat': 'Sum'
                    }
                },
                {
                    'Id': 'writeBytes',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/EBS',
                            'MetricName': 'VolumeWriteBytes',
                            'Dimensions': [{'Name': 'VolumeId', 'Value': volume_id}]
                        },
                        'Period': 300,
                        'Stat': 'Sum'
                    }
                }
            ],
            StartTime=start_time,
            EndTime=end_time
        )
        
        # Extract metric values
        read_bytes_values, write_bytes_values, timestamps = [], [], []
        for result in response.get('MetricDataResults', []):
            if result.get('Id') == 'readBytes':
                read_bytes_values = result.get('Values', [])
                timestamps = result.get('Timestamps', [])
            elif result.get('Id') == 'writeBytes':
                write_bytes_values = result.get('Values', [])
        
        # Compute max throughput in MBps
        max_throughput, max_throughput_timestamp = 0, None
        if len(read_bytes_values) == len(write_bytes_values) == len(timestamps):
            for i in range(len(read_bytes_values)):
                current_throughput = (read_bytes_values[i] + write_bytes_values[i]) / (300 * 1024 * 1024)
                if current_throughput > max_throughput:
                    max_throughput = current_throughput
                    max_throughput_timestamp = timestamps[i]
        
        return max_throughput, max_throughput_timestamp
    except Exception as e:
        print(f"Error retrieving CloudWatch metrics for volume {volume_id}: {e}")
        return 0, None

def main():
    """
    Main function to analyze EBS volumes and report unused IOPS and throughput.
    """
    volumes_response = ec2_client.describe_volumes(
        Filters=[{'Name': 'tag_name', 'Values': ['tag_value']}]
    )
    volumes = volumes_response.get('Volumes', [])
    filtered_volumes = [vol for vol in volumes if vol.get('Size', 0) > 150 and vol.get('Iops', 0) > 3000]
    
    if not filtered_volumes:
        print("No volumes found meeting the criteria.")
        return
    
    print("volume_id,type,size,iops,throughput,instance_id,instance_type,instancename,max_iops,max_throughput")
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(days=60)
    
    for volume in filtered_volumes:
        volume_id = volume.get('VolumeId', '')
        max_iops, _, _, _ = get_max_iops(volume_id, cloudwatch_client, start_time, end_time)
        max_throughput, _ = get_max_throughput(volume_id, cloudwatch_client, start_time, end_time)
        print(f"{volume_id},{max_iops},{max_throughput}")

if __name__ == "__main__":
    main()
