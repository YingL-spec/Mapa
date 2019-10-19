
import torch
import torch.nn as nn
import torch.utils.data as Data
import torchvision,time
import os, math,queue, random
import paho.mqtt.client as mqtt
import _pickle as cPickle
from math import sqrt
import numpy as np

EPOCH = int(os.environ.get('EPOCH') )
DELAY = int(os.environ.get('DELAY') )
BATCH_SIZE = int(os.environ.get('BATCH_SIZE') )
MQTT_PORT = int(os.environ.get('MQTT_PORT'))
MQTT_IP = os.environ.get('MQTT_IP')
TEST_NUM = int(os.environ.get('TEST_NUM') )
DATA_ROOT = os.environ.get('DATA_ROOT')
RESULT_ROOT = os.environ.get('RESULT_ROOT')
CLIENT_ID =  str(random.random())
isSecondStep = False
m=60000

T=math.floor(m/BATCH_SIZE)*EPOCH
train_data = torchvision.datasets.MNIST(
    root=DATA_ROOT,
    train=True,                                     
    transform=torchvision.transforms.ToTensor(),    
)
train_loader = Data.DataLoader(dataset=train_data, batch_size=BATCH_SIZE, shuffle=True)
test_data = torchvision.datasets.MNIST(root=DATA_ROOT, train=False)
test_x = torch.unsqueeze(test_data.test_data, dim=1).type(torch.FloatTensor)[:10000] 
test_y = test_data.test_labels[:10000]

def norm(grads):
    grads_ = []
    for i in range(len(grads)):
        grads_.extend(list(grads[i].ravel()))
    grads_ = np.array(grads_)
    norm = np.linalg.norm(grads_,ord=2) 
    return norm

class CNN(nn.Module):
    def __init__(self):
        super(CNN, self).__init__()
        self.conv1 = nn.Sequential(        
            nn.Conv2d(
                in_channels=1,            
                out_channels=10,         
                kernel_size=5, 
                            
                  ),                           
            nn.ReLU(),                   
            nn.MaxPool2d(2),    
        )
        self.conv2 = nn.Sequential(      
            nn.Conv2d(
                in_channels=10,          
                out_channels=10,         
                kernel_size=5,  
                     
                ),    
            nn.ReLU(),                     
            nn.MaxPool2d(2),               
        )
        self.out = nn.Linear(10 * 4 * 4, 10)  
        
    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = x.view(x.size(0), -1)         
        output = self.out(x)
        return output, x   

cnn = CNN()
acc =[]
msgQueue = queue.Queue()

def on_message(mqttc, obj, msg):
    print("received: " + msg.topic + " " + str(msg.qos))
    if msg.topic == "ts_two_paramas_to_cloud":
        global isSecondStep
        mqttc.unsubscribe("ts_params/" + CLIENT_ID)
        msgQueue.queue.clear()
        msgQueue.put(msg.payload)
        isSecondStep = True
    else:
        msgQueue.put(msg.payload)
        
client = mqtt.Client(client_id = CLIENT_ID)
client.on_message = on_message
client.connect(MQTT_IP,MQTT_PORT, 600)
client.subscribe([("ts_init_params", 2),("ts_params/" + CLIENT_ID, 2), ("ts_two_paramas_to_cloud", 2), ("ts_params2/" + CLIENT_ID, 2),])
client.loop_start()

if __name__=='__main__':
    acc =[]
    params = cPickle.loads(msgQueue.get())
    strat_time = time.time()
    for i,f in enumerate(cnn.parameters()):
        f.data = params[i].float()
    for epoch in range(EPOCH):
        for step, (b_x, b_y) in enumerate(train_loader):  
            output = cnn.forward(b_x)[0] 
            loss = nn.CrossEntropyLoss()(output, b_y)
            cnn.zero_grad()  
            loss.backward()    
        
            if step % TEST_NUM == 0:
                man_file = open(RESULT_ROOT+str(DELAY)+'-ts.txt', 'w')
                test_output, last_layer = cnn(test_x)
                pred_y = torch.max(test_output, 1)[1].data.numpy()
                accuracy = float((pred_y == test_y.data.numpy()).astype(int).sum()) / float(test_y.size(0))
                acc.append(accuracy)
                print(acc,file=man_file)
                man_file.close()
            
            w_c1 = cnn.conv1[0].weight.grad
            b_c1 = cnn.conv1[0].bias.grad
        
            w_c2 = cnn.conv2[0].weight.grad
            b_c2 = cnn.conv2[0].bias.grad

            w_o = cnn.out.weight.grad
            b_o = cnn.out.bias.grad       
            
            grads = [w_c1,b_c1,w_c2,b_c2,w_o,b_o]
            if isSecondStep:
                break
            if  (epoch*(m/BATCH_SIZE)+step)>=0.4*T:
                print("two stage")
                client.publish("ts_two_paramas_to_cloud", cPickle.dumps(params), 2)
                isSecondStep =True
                break
            else:
                client.publish("ts_grads/" + CLIENT_ID, cPickle.dumps(grads), 2)
            params = cPickle.loads(msgQueue.get())
            for i,f in enumerate(cnn.parameters()):
                f.data = params[i].float()
           
        if isSecondStep:
                break

    if not msgQueue.empty():
        params = cPickle.loads(msgQueue.get())
        for i,f in enumerate(cnn.parameters()):
                f.data = params[i].float() 

    for epoch in range(EPOCH):
        for step, (b_x, b_y) in enumerate(train_loader):
            output = cnn.forward(b_x)[0] 
            loss = nn.CrossEntropyLoss()(output, b_y)
            cnn.zero_grad()  
            loss.backward()  
            if step % TEST_NUM == 0:
                man_file = open(RESULT_ROOT+str(DELAY)+'-ts.txt', 'w')
                test_output, last_layer = cnn(test_x)
                pred_y = torch.max(test_output, 1)[1].data.numpy()
                accuracy = float((pred_y == test_y.data.numpy()).astype(int).sum()) / float(test_y.size(0))
                acc.append(accuracy)
                print(acc,file=man_file)
                man_file.close()

            w_c1 = cnn.conv1[0].weight.grad
            b_c1 = cnn.conv1[0].bias.grad
           
            w_c2 = cnn.conv2[0].weight.grad
            b_c2 = cnn.conv2[0].bias.grad

            w_o = cnn.out.weight.grad
            b_o = cnn.out.bias.grad       
            
            grads = [w_c1,b_c1,w_c2,b_c2,w_o,b_o]
            client.publish("ts_grads2/" + CLIENT_ID, cPickle.dumps(grads), 2)
            params = cPickle.loads(msgQueue.get())
            for i,f in enumerate(cnn.parameters()):
                f.data = params[i].float()
            
   
 
    