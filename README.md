# HotelSriKrishna-Backend

1. Set Up EC2 Instance 
2. Set Up Security Group 
3. Set Up Elastic IP



1. Set Up an EC2 Instance
Login to AWS Console: bishnu.mishra1987@gmail.com	
		      HSK@2024

Go to EC2 Dashboard > Launch Instance.
1) Choose an Amazon Linux 2 AMI (Free Tier eligible).
2) Select t2.micro (Free Tier eligible).
3) Choose the default VPC and subnet (leave everything as is for now).
For Security Group, allow HTTP (port 80), HTTPS (port 443), and SSH (port 22) to be accessible.
4) Create a new key pair for SSH access to the instance (make sure to download the .pem file). HSK PPK ( converted using Puttygen)
Launch the instance.
5) Security Group - SSH 22 , TCP 3000, TCP 5000, HTTP 80 
6) Get the Public IP Address of your EC2 instance from the EC2 dashboard.
7) Access using publicIP 
8) 


Open the instance using Putty 
user - ec2-user 

Installation 
sudo yum install python3 -y
sudo yum install python3-pip -y
sudo pip3 install gunicorn
sudo curl --silent --location https://rpm.nodesource.com/setup_16.x | sudo bash -
sudo yum install nodejs -y
sudo yum install git -y
sudo amazon-linux-extras enable nginx1.12
sudo yum install nginx -y



cd /home/ec2-user
git clone https://github.com/yourusername/your-repository.git
cd your-repository

Backend Set Up 
------------------------------------

python3 -m venv venv
source venv/bin/activate

pip install flask
pip install gunicorn
pip install -r requirements.txt
nohup gunicorn --bind 0.0.0.0:5000 app:applicaion > gunicorn.log 2>&1 &

Run as a Service 
----------------

sudo vi /etc/systemd/system/gunicorn.service

[Unit]
Description=Gunicorn instance for Hotel Sri Krishna
After=network.target

[Service]
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/your_project
ExecStart=/home/ec2-user/your_project/venv/bin/gunicorn --bind 0.0.0.0:5000 app:application > gunicorn.log 2>&1 &

Restart=always

[Install]
WantedBy=multi-user.target

sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn  # Start on boot



FRONTEND SET UP


cd /home/ec2-user/HotelSriKrishna-Frontend/frontend

npm install
npm run build


sudo nano /etc/nginx/nginx.conf

server {
    listen 80;
    server_name _;

    location / {
        root /home/ec2-user/HotelSriKrishna-Frontend/build;
        try_files $uri /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000;  # Flask app running on Gunicorn
    }
}


sudo systemctl restart nginx




sudo chmod -R 755 /home/ec2-user/HotelSriKrishna-Frontend/build
sudo chmod -R 755 /home/ec2-user/HotelSriKrishna-Frontend
sudo chmod +x /home/ec2-user
sudo chown -R nginx:nginx /home/ec2-user/HotelSriKrishna-Frontend/build
sudo chmod +x /home/ec2-user
sudo systemctl restart nginx
sudo systemctl status nginx  # Check if it's running








notepad C:\Windows\System32\drivers\etc\hosts
