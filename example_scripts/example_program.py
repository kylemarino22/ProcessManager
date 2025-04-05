import time

count = 0
while True:
    
    time.sleep(10)
    
    print("Slept 10 seconds!")

    if count == 3:
        raise Exception("Program failed! :((")

    count += 1