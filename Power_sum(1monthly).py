import time

import requests
import json
import pandas as pd

P_n = 600  # 机组额定容量
gyDataUrl = " http://192.168.240.190:1338/api/pfr"
pyDataUrl=" http://192.168.240.190:1338/api/map"
url = f"{gyDataUrl}/monthly"
print(url)

if __name__ == '__main__':
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    print(data)
    regulationCount = data[0]['regulationCount']  # 一次调频动作次数
    smallFreqCount = data[0]['smallFreqCount']  # 小频差一次调频动作次数
    largeFreqCount = data[0]['largeFreqCount']  # 大频差一次调频动作次数
    unqualifiedCount = data[0]['unqualifiedCount']  # 一次调频动作不合格次数
    exitTime = data[0]['exitTime']  # 退出时间
    smallUnqCount = data[0]['smallUnqCount']  # 小频差扰动不合格次数
    largeUnqCount = data[0]['largeUnqCount']  # 小频差扰动不合格次数
    qualified_rate = round(unqualifiedCount / regulationCount, 2)
    print(qualified_rate)
    # ***************************小扰动考核电量**********************
    small_examine_P = 0.03 * P_n * smallUnqCount
    if qualified_rate >= 0.8:
        if small_examine_P > P_n:
            small_examine_P = P_n
    if 0.5 < qualified_rate < 0.8:
        if small_examine_P > 2 * P_n:
            small_examine_P = 2 * P_n
    if qualified_rate <= 0.5:
        if small_examine_P > 3 * P_n:
            small_examine_P = 3 * P_n
    print("当月小扰动考核电量" + str(small_examine_P))
    # ***************************大扰动考核电量**********************
    large_examine_P = 0.3 * P_n * 0

    print("当月大扰动考核电量" + str(large_examine_P))
    # ***************************退出时间考核电量**********************
    exitTime_examine_P = 0.02 * P_n * (exitTime / 3600)
    print("当月退出时间考核电量" + str(exitTime_examine_P))

    sum_examine_P = large_examine_P + exitTime_examine_P + small_examine_P
    print("当月考核电量" + str(sum_examine_P))
    # ***************************判断数据是否存在**********************
    response = requests.get(pyDataUrl)
    response.raise_for_status()
    data = response.json()
    df = pd.DataFrame(data)
    current_month = time.strftime("%Y-%m", time.localtime())
    month = df.iloc[:, 1].tolist()
    if current_month in month:
        print("数据已存在")
    else:
        return_dict = {
            "month":  time.strftime("%Y-%m", time.localtime()),
            "value": sum_examine_P+1000,
        }
        print(return_dict)
        response = requests.post(pyDataUrl,json=return_dict)
        print(response.text)