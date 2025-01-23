import pandas as pd
import openpyxl
import numpy as np
import time
import requests
import json

K_C = 0.05  # 机组调差系数
P_n = 600  # 机组额定容量
multiplier = 60
global D_Disturbance_mon_qualified_sum, S_Disturbance_mon_qualified_sum, D_Disturbance_mon_unqualified_sum, \
    S_Disturbance_mon_unqualified_sum, Initial_Position, tuichu_time, last_disturbance_time, contribution_K  # 机组大频差扰动合格次数
pyDataUrl = "http://192.168.240.190:1338/api/pfr"
gyDataUrl = " http://192.168.240.190:1337/api/rekong"
read_hour_url = f"{gyDataUrl}/hour"


# ****************************读取文件接口*******************************
def read_excel():
    df = pd.read_excel('5.xlsx', sheet_name=0, keep_default_na=False)
    data_df = pd.DataFrame(df)
    pinlv = data_df.iloc[:, 4].values
    for i in range(len(pinlv)):
        pinlv[i] *= multiplier
    toutui = data_df.iloc[:, 6].values
    fuhe = data_df.iloc[:, 5].values
    return pinlv, toutui, fuhe


# ****************************读取ICS数据接口*******************************
def read_SIS():
    pinlv_average = []
    response = requests.get(read_hour_url)
    response.raise_for_status()
    data = response.json()
    df = pd.DataFrame(data)
    pinlv1 = df.loc[df['code'] == '2DCS_20YHTCB_FRE1', :].value.to_list()
    pinlv2 = df.loc[df['code'] == '2DCS_20YHTCB_FRE2', :].value.to_list()
    pinlv3 = df.loc[df['code'] == '2DCS_20YHTCB_FRE3', :].value.to_list()
    fuhe = df.loc[df['code'] == '2DCS_SE1_F_W1', :].value.to_list()
    toutui = df.loc[df['code'] == '2DCS_20MYA01DU052_XT01', :].value.to_list()
    for i in range(0, len(pinlv1)):
        a = round((pinlv1[i] + pinlv2[i] + pinlv3[i]) / 3, 3)
        a *= multiplier
        pinlv_average.append(a)
    #print(toutui)
    return pinlv_average, toutui, fuhe


# *************************大频差有效扰动判断************************
def D_disturbance_Effective(start_time, end_time):
    if end_time - start_time > 3:
        D_flag = 1
    else:
        D_flag = 0
    return D_flag


# *************************小频差有效扰动判断************************
def S_disturbance_Effective(start_time, end_time, pinlv_value, Adequate_spacing):
    if end_time - start_time >= 17:
        if abs(pinlv_value[start_time - 3] - 3000) <= 2:
            if abs(pinlv_value[start_time - 2] - 3000) <= 2:
                if abs(pinlv_value[start_time - 1] - 3000) <= 2:
                    wending = 1
                else:
                    wending = 0
            else:
                wending = 0
        else:
            wending = 0
        if wending == 1:
            if Adequate_spacing == 1:
                S_flag = 1
            else:
                S_flag = 0
        else:
            S_flag = 0
    else:
        S_flag = 0

    return S_flag


# *************************计算一次调频贡献率K************************
def K_calculate(start_time, end_time, P_in, k_pinlv_value, k_fuhe_value):
    f_current = 0
    P_current = 0
    P_theory_sum = 0
    power_actual_sum = 0
    power_actual = 0
    if end_time - start_time > 60:
        end_time = start_time + 60
    Duration_time = end_time - start_time
    # 理论一次调频积分电量
    for q in range(0, Duration_time):
        f_current = abs(k_pinlv_value[q] / 60 - 50) - 0.033
        P_current = -(f_current / (50 * K_C)) * P_n
        P_theory_sum = P_theory_sum + P_current
    # 实际积分电量计算
    for u in range(0, Duration_time):
        power_actual = k_fuhe_value[u] - P_in  # 当前时刻实际贡献电量
        power_actual_sum = power_actual_sum + power_actual  # 一次调频动作期间实际累加贡献电量
    K = abs(power_actual_sum / P_theory_sum)
    #print("当前一次调频贡献率为" + str(K))
    return K


# *********************************大偏差扰动贡献率、调节精度计算*******************
def D_parameter_calculation(D_K):
    if D_K >= 0.8:
        D_N_contribution = 1
    else:
        D_N_contribution = 0
    if D_K <= 1.3:
        D_N_Adjusting = 1
    else:
        D_N_Adjusting = 0
    return D_N_contribution, D_N_Adjusting


# *********************************小偏差扰动贡献率、调节精度计算*******************
def S_parameter_calculation(S_K, fuhe_average, pinlv_min):
    if fuhe_average > 240:
        if S_K >= 0.5:
            S_N_contribution = 1
        else:
            S_N_contribution = 0
    else:
        if S_K >= 0.4:
            S_N_contribution = 1
        else:
            S_N_contribution = 0
    if abs(pinlv_min - 3000) < 3.6:
        if S_K <= 2.3:
            S_N_Adjusting = 1
        else:
            S_N_Adjusting = 0
    else:
        if S_K <= 1.5:
            S_N_Adjusting = 1
        else:
            S_N_Adjusting = 0
    return S_N_contribution, S_N_Adjusting


# *********************************大偏差响应滞后时间计算*******************
def D_Response_lag_time(P_init, fuhe):
    lag_time = 0
    for t in range(0, len(fuhe)):
        if fuhe[t] - P_init > 0.1:
            lag_time = t
            break
    if lag_time < 3:
        lag_time_flag = 1
    else:
        lag_time_flag = 0
    return lag_time, lag_time_flag


# *********************************大偏差扰动合格判断*******************
def D_qualified_judgment(N_N, N_T, N_T_L):
    D_qualified_flag = 1 - N_N * N_T * N_T_L
    return D_qualified_flag


# *********************************小偏差扰动合格判断*******************
def S_qualified_judgment(N_N, N_T):
    S_qualified_flag = 1 - N_N * N_T
    return S_qualified_flag


# *********************************主体循环函数*******************
def main_process(pinlv_value, toutui_value, fuhe_value):
    global D_Disturbance_mon_qualified_sum, S_Disturbance_mon_qualified_sum, D_Disturbance_mon_unqualified_sum, \
        S_Disturbance_mon_unqualified_sum, Initial_Position, tuichu_time, last_disturbance_time, last_disturbance_time, \
        contribution_K  # 机组大频差扰动合格次数
    t = time.localtime()
    last_disturbance_time = 0
    for i in range(Initial_Position, len(pinlv_value)):
        if fuhe_value[i] < 20:
            #print("当前机组停机")
            return
        if toutui_value[i] == 0:
            #print("一次调频功能退出")
            tuichu_time = tuichu_time + 1

        if toutui_value[i] == 1:
            # if fuhe_value[i] <= 180:
            #     print("当前负荷低于机组额定容量的30%，一次调频功能免于考核")
            if 180 < fuhe_value[i] <= 210:
                #   print("当前负荷低于机组额定容量的35%，一次调频减负荷功能免于考核")
                # if -2 <= pinlv_value[i] - 3000 <= 2:
                #     print("当前一次调频未动作")
                # *****************************一次调频减出力*****************************
                if pinlv_value[i] - 3000 > 2:
                    R_action_start_time = i  # 反向动作时间开始
                    if R_action_start_time + 180 > len(pinlv_value):
                        R_find_time = len(pinlv_value) - 1
                    else:
                        R_find_time = R_action_start_time + 180
                    for a in range(R_action_start_time, R_find_time):  # 一次调频最大动作时间为60S
                        if pinlv_value[a] - 3000 <= 2:
                            R_action_end_time = a  # 反向动作时间结束
                            Initial_Position = a
                            #print("当前负荷低于机组额定容量的35%,该次调频为减出力，该次不予统计")
                            return

                # *****************************一次调频增出力*****************************
                if pinlv_value[i] - 3000 < -2:
                    P_action_start_time = i  # 正向动作时间开始
                    if P_action_start_time < 20:
                        Adequate_spacing_flag = 1
                    else:
                        if P_action_start_time - last_disturbance_time > 20:
                            #print("两次扰动时间间隔大于20S")
                            Adequate_spacing_flag = 1
                        else:
                            Adequate_spacing_flag = 0
                    contribution_rate_K = 0
                    if P_action_start_time < 3:
                        P_initial_value = fuhe_value[P_action_start_time]
                    else:
                        P_initial_value = np.mean(fuhe_value[P_action_start_time - 3: P_action_start_time])
                    if P_action_start_time + 180 > len(pinlv_value):
                        P_find_time = len(pinlv_value) - 1
                    else:
                        P_find_time = P_action_start_time + 180
                    for a in range(P_action_start_time, P_find_time):  # 一次调频最大动作时间为60S
                        if pinlv_value[a] - 3000 >= -2:
                            P_action_end_time = a  # 反向动作时间结束
                            Initial_Position = a

                            last_disturbance_time = a
                            #print("当前负荷低于机组额定容量的35%,该次调频为增出力，该次统计")
                            print(pinlv_value[P_action_start_time: P_action_end_time])
                            fuhe_disturbance_average = np.mean(fuhe_value[P_action_start_time: P_action_end_time])
                            pinlv_min_value = min(pinlv_value[P_action_start_time: P_action_end_time])
                            #print("增出力最小频率为" + str(pinlv_min_value))
                            if pinlv_min_value <= 2995.2:
                                print("当前为大频差扰动")
                                D_Valid_Flag = D_disturbance_Effective(P_action_start_time, P_action_end_time)
                                if D_Valid_Flag == 1:
                                    contribution_rate_K = K_calculate(P_action_start_time, P_action_end_time,
                                                                      P_initial_value,
                                                                      pinlv_value[
                                                                      P_action_start_time:P_action_end_time],
                                                                      fuhe_value[P_action_start_time:P_action_end_time])
                                    contribution_K.append(contribution_rate_K)
                                    D_N_contribution_result, D_N_Adjusting_result = D_parameter_calculation(
                                        contribution_rate_K)
                                    N_lag_time, N_lag_time_result = D_Response_lag_time(P_initial_value,
                                                                                        fuhe_value[
                                                                                        P_action_start_time:P_action_end_time])

                                    # print("当前为大频差扰动,当前扰动一次调频动作贡献率为" + str(contribution_rate_K))
                                    # print("当前为大频差扰动,当前扰动一次调频动作贡献率取值为" + str(D_N_contribution_result))
                                    # print("当前为大频差扰动,当前扰动一次调频动作调频精度取值为" + str(D_N_Adjusting_result))
                                    # print("当前为大频差扰动,当前扰动一次调频动作滞后时间为" + str(N_lag_time))
                                    # print("当前为大频差扰动,当前扰动一次调频动作滞后时间取值为" + str(N_lag_time_result))
                                    D_qualified_result_flag = D_qualified_judgment(D_N_contribution_result,
                                                                                   D_N_Adjusting_result,
                                                                                   N_lag_time_result)
                                    if D_qualified_result_flag == 0:
                                        #print("当前大频差扰动合格")
                                        D_Disturbance_mon_qualified_sum[t.tm_mon] = D_Disturbance_mon_qualified_sum[
                                                                                        t.tm_mon] + 1
                                        #print("当前大频差扰动合格次数：" + str(D_Disturbance_mon_qualified_sum))
                                        return
                                    if D_qualified_result_flag == 1:
                                        #print("当前大频差扰动不合格")
                                        D_Disturbance_mon_unqualified_sum[t.tm_mon] = D_Disturbance_mon_unqualified_sum[
                                                                                          t.tm_mon] + 1
                                        #print("当前大频差扰动不合格次数：" + str(D_Disturbance_mon_unqualified_sum))
                                        return
                                else:
                                    return

                            if pinlv_min_value > 2995.2:

                                S_Valid_Flag = S_disturbance_Effective(P_action_start_time, P_action_end_time,
                                                                       pinlv_value, Adequate_spacing_flag)
                                if S_Valid_Flag == 1:
                                    contribution_rate_K = K_calculate(P_action_start_time, P_action_end_time,
                                                                      P_initial_value,
                                                                      pinlv_value[
                                                                      P_action_start_time:P_action_end_time],
                                                                      fuhe_value[P_action_start_time:P_action_end_time])
                                    contribution_K.append(contribution_rate_K)
                                    S_N_contribution_result, S_N_Adjusting_result = S_parameter_calculation(
                                        contribution_rate_K, fuhe_disturbance_average, pinlv_min_value)
                                    S_qualified_result_flag = S_qualified_judgment(S_N_contribution_result,
                                                                                   S_N_Adjusting_result)
                                    if S_qualified_result_flag == 0:
                                        #print("当前小频差扰动合格")
                                        S_Disturbance_mon_qualified_sum[t.tm_mon] = S_Disturbance_mon_qualified_sum[
                                                                                        t.tm_mon] + 1
                                        #print("当前小频差扰动合格次数：" + str(S_Disturbance_mon_qualified_sum))
                                        return
                                    if S_qualified_result_flag == 1:
                                        #print("当前小频差扰动不合格")
                                        S_Disturbance_mon_unqualified_sum[t.tm_mon] = S_Disturbance_mon_unqualified_sum[
                                                                                          t.tm_mon] + 1
                                        #print("当前小频差扰动不合格次数：" + str(S_Disturbance_mon_unqualified_sum))
                                        return
                                else:
                                    return
            if 210 < fuhe_value[i]:
                # print("当前负荷大于机组额定容量的35%，一次调频功能正常考核")
                # if -2 <= pinlv_value[i] - 3000 <= 2:
                #   print("当前一次调频未动作")
                # *****************************一次调频减出力*****************************
                if pinlv_value[i] - 3000 > 2:
                    R_action_start_time = i  # 反向动作时间开始
                    if R_action_start_time < 20:
                        Adequate_spacing_flag = 1
                    else:
                        if R_action_start_time - last_disturbance_time > 20:
                            #print("两次扰动时间间隔大于20S")
                            Adequate_spacing_flag = 1
                        else:
                            Adequate_spacing_flag = 0
                    contribution_rate_K = 0
                    if R_action_start_time < 3:
                        R_initial_value = fuhe_value[R_action_start_time]
                    else:
                        R_initial_value = np.mean(fuhe_value[R_action_start_time - 3: R_action_start_time])
                    if R_action_start_time + 180 > len(pinlv_value):
                        R_find_time = len(pinlv_value) - 1
                    else:
                        R_find_time = R_action_start_time + 180
                    for a in range(R_action_start_time, R_find_time):  # 一次调频最大动作时间为60S
                        if pinlv_value[a] - 3000 <= 2:
                            R_action_end_time = a  # 反向动作时间结束
                            Initial_Position = a
                            last_disturbance_time = a
                            print(pinlv_value[R_action_start_time: R_action_end_time])
                            fuhe_disturbance_average = np.mean(fuhe_value[R_action_start_time: R_action_end_time])
                            pinlv_max_value = max(pinlv_value[R_action_start_time: R_action_end_time])
                            #print("减出力最大频率为" + str(pinlv_max_value))
                            if pinlv_max_value > 3004.8:
                                #print("当前为大频差扰动")
                                D_Valid_Flag = D_disturbance_Effective(R_action_start_time, R_action_end_time)
                                if D_Valid_Flag == 1:
                                    contribution_rate_K = K_calculate(R_action_start_time, R_action_end_time,
                                                                      R_initial_value,
                                                                      pinlv_value[
                                                                      R_action_start_time:R_action_end_time],
                                                                      fuhe_value[R_action_start_time:R_action_end_time])
                                    contribution_K.append(contribution_rate_K)
                                    D_N_contribution_result, D_N_Adjusting_result = D_parameter_calculation(
                                        contribution_rate_K)
                                    N_lag_time, N_lag_time_result = D_Response_lag_time(R_initial_value,
                                                                                        fuhe_value[
                                                                                        R_action_start_time:R_action_end_time])

                                    # print("当前为大频差扰动,当前扰动一次调频动作贡献率为" + str(contribution_rate_K))
                                    # print("当前为大频差扰动,当前扰动一次调频动作贡献率取值为" + str(D_N_contribution_result))
                                    # print("当前为大频差扰动,当前扰动一次调频动作调频精度取值为" + str(D_N_Adjusting_result))
                                    # print("当前为大频差扰动,当前扰动一次调频动作滞后时间为" + str(N_lag_time))
                                    # print("当前为大频差扰动,当前扰动一次调频动作滞后时间取值为" + str(N_lag_time_result))
                                    D_qualified_result_flag = D_qualified_judgment(D_N_contribution_result,
                                                                                   D_N_Adjusting_result,
                                                                                   N_lag_time_result)
                                    if D_qualified_result_flag == 0:
                                        #print("当前大频差扰动合格")
                                        D_Disturbance_mon_qualified_sum[t.tm_mon] = D_Disturbance_mon_qualified_sum[
                                                                                        t.tm_mon] + 1
                                        #print("当前大频差扰动合格次数：" + str(D_Disturbance_mon_qualified_sum))
                                        return
                                    if D_qualified_result_flag == 1:
                                        #print("当前大频差扰动不合格")
                                        D_Disturbance_mon_unqualified_sum[t.tm_mon] = D_Disturbance_mon_unqualified_sum[
                                                                                          t.tm_mon] + 1
                                        #print("当前大频差扰动不合格次数：" + str(D_Disturbance_mon_unqualified_sum))
                                        return
                                else:
                                    return
                            if pinlv_max_value <= 3004.8:
                                #print("当前为小频差扰动")
                                S_Valid_Flag = S_disturbance_Effective(R_action_start_time, R_action_end_time,
                                                                       pinlv_value, Adequate_spacing_flag)
                                if S_Valid_Flag == 1:
                                    contribution_rate_K = K_calculate(R_action_start_time, R_action_end_time,
                                                                      R_initial_value,
                                                                      pinlv_value[
                                                                      R_action_start_time:R_action_end_time],
                                                                      fuhe_value[R_action_start_time:R_action_end_time])
                                    contribution_K.append(contribution_rate_K)
                                    S_N_contribution_result, S_N_Adjusting_result = S_parameter_calculation(
                                        contribution_rate_K, fuhe_disturbance_average, pinlv_max_value)
                                    S_qualified_result_flag = S_qualified_judgment(S_N_contribution_result,
                                                                                   S_N_Adjusting_result)
                                    if S_qualified_result_flag == 0:
                                        #print("当前小频差扰动合格")
                                        S_Disturbance_mon_qualified_sum[t.tm_mon] = S_Disturbance_mon_qualified_sum[
                                                                                        t.tm_mon] + 1
                                        #print("当前小频差扰动合格次数：" + str(S_Disturbance_mon_qualified_sum))
                                        return
                                    if S_qualified_result_flag == 1:
                                        #print("当前小频差扰动不合格")
                                        S_Disturbance_mon_unqualified_sum[t.tm_mon] = S_Disturbance_mon_unqualified_sum[
                                                                                          t.tm_mon] + 1
                                        #print("当前小频差扰动不合格次数：" + str(S_Disturbance_mon_unqualified_sum))
                                        return
                                else:
                                    return
                # *****************************一次调频增出力*****************************
                if pinlv_value[i] - 3000 < -2:
                    P_action_start_time = i  # 正向动作时间开始
                    if P_action_start_time < 20:
                        Adequate_spacing_flag = 1
                    else:
                        if P_action_start_time - last_disturbance_time > 20:
                            #print("两次扰动时间间隔大于20S")
                            Adequate_spacing_flag = 1
                        else:
                            Adequate_spacing_flag = 0
                    contribution_rate_K = 0
                    if P_action_start_time < 3:
                        P_initial_value = fuhe_value[P_action_start_time]
                    else:
                        P_initial_value = np.mean(fuhe_value[P_action_start_time - 3: P_action_start_time])
                    if P_action_start_time + 180 > len(pinlv_value):
                        P_find_time = len(pinlv_value) - 1
                    else:
                        P_find_time = P_action_start_time + 180
                    for a in range(P_action_start_time, P_find_time):  # 一次调频最大动作时间为60S
                        if pinlv_value[a] - 3000 >= -2:
                            P_action_end_time = a  # 反向动作时间结束
                            Initial_Position = a

                            last_disturbance_time = a
                            print(pinlv_value[P_action_start_time: P_action_end_time])
                            fuhe_disturbance_average = np.mean(fuhe_value[P_action_start_time: P_action_end_time])
                            pinlv_min_value = min(pinlv_value[P_action_start_time: P_action_end_time])
                            #print("增出力最小频率为" + str(pinlv_min_value))
                            if pinlv_min_value <= 2995.2:
                                #print("当前为大频差扰动")
                                D_Valid_Flag = D_disturbance_Effective(P_action_start_time, P_action_end_time)
                                if D_Valid_Flag == 1:
                                    contribution_rate_K = K_calculate(P_action_start_time, P_action_end_time,
                                                                      P_initial_value,
                                                                      pinlv_value[
                                                                      P_action_start_time:P_action_end_time],
                                                                      fuhe_value[P_action_start_time:P_action_end_time])
                                    contribution_K.append(contribution_rate_K)
                                    D_N_contribution_result, D_N_Adjusting_result = D_parameter_calculation(
                                        contribution_rate_K)
                                    N_lag_time, N_lag_time_result = D_Response_lag_time(P_initial_value,
                                                                                        fuhe_value[
                                                                                        P_action_start_time:P_action_end_time])

                                    # print("当前为大频差扰动,当前扰动一次调频动作贡献率为" + str(contribution_rate_K))
                                    # print("当前为大频差扰动,当前扰动一次调频动作贡献率取值为" + str(D_N_contribution_result))
                                    # print("当前为大频差扰动,当前扰动一次调频动作调频精度取值为" + str(D_N_Adjusting_result))
                                    # print("当前为大频差扰动,当前扰动一次调频动作滞后时间为" + str(N_lag_time))
                                    # print("当前为大频差扰动,当前扰动一次调频动作滞后时间取值为" + str(N_lag_time_result))
                                    D_qualified_result_flag = D_qualified_judgment(D_N_contribution_result,
                                                                                   D_N_Adjusting_result,
                                                                                   N_lag_time_result)
                                    if D_qualified_result_flag == 0:
                                        #print("当前大频差扰动合格")
                                        D_Disturbance_mon_qualified_sum[t.tm_mon] = D_Disturbance_mon_qualified_sum[
                                                                                        t.tm_mon] + 1
                                        #print("当前大频差扰动合格次数：" + str(D_Disturbance_mon_qualified_sum))
                                        return
                                    if D_qualified_result_flag == 1:
                                        #print("当前大频差扰动不合格")
                                        D_Disturbance_mon_unqualified_sum[t.tm_mon] = D_Disturbance_mon_unqualified_sum[
                                                                                          t.tm_mon] + 1
                                        #print("当前大频差扰动不合格次数：" + str(D_Disturbance_mon_unqualified_sum))
                                        return
                                else:
                                    return

                            if pinlv_min_value > 2995.2:
                                #print("当前为小频差扰动")
                                S_Valid_Flag = S_disturbance_Effective(P_action_start_time, P_action_end_time,
                                                                       pinlv_value, Adequate_spacing_flag)
                                if S_Valid_Flag == 1:
                                    contribution_rate_K = K_calculate(P_action_start_time, P_action_end_time,
                                                                      P_initial_value,
                                                                      pinlv_value[
                                                                      P_action_start_time:P_action_end_time],
                                                                      fuhe_value[P_action_start_time:P_action_end_time])
                                    contribution_K.append(contribution_rate_K)
                                    S_N_contribution_result, S_N_Adjusting_result = S_parameter_calculation(
                                        contribution_rate_K, fuhe_disturbance_average, pinlv_min_value)
                                    S_qualified_result_flag = S_qualified_judgment(S_N_contribution_result,
                                                                                   S_N_Adjusting_result)
                                    if S_qualified_result_flag == 0:
                                        #print("当前小频差扰动合格")
                                        S_Disturbance_mon_qualified_sum[t.tm_mon] = S_Disturbance_mon_qualified_sum[
                                                                                        t.tm_mon] + 1
                                        #print("当前小频差扰动合格次数：" + str(S_Disturbance_mon_qualified_sum))
                                        return
                                    if S_qualified_result_flag == 1:
                                        #print("当前小频差扰动不合格")
                                        S_Disturbance_mon_unqualified_sum[t.tm_mon] = S_Disturbance_mon_unqualified_sum[
                                                                                          t.tm_mon] + 1
                                        #print("当前小频差扰动不合格次数：" + str(S_Disturbance_mon_unqualified_sum))
                                        return
                                else:
                                    return
        if i == len(pinlv_value) - 1:
            Initial_Position = i + 1
            return Initial_Position

    return Initial_Position


if __name__ == '__main__':
    pinlv, toutui, fuhe = read_SIS()
    t1 = time.localtime()
    contribution_K = []
    D_Disturbance_mon_qualified_sum = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # 本次运行大扰动频差合格次数
    S_Disturbance_mon_qualified_sum = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # 本次运行小扰动频差合格次数
    D_Disturbance_mon_unqualified_sum = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # 本次运行大扰动频差不合格次数
    S_Disturbance_mon_unqualified_sum = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # 本次运行小扰动频差不合格次数
    Initial_Position = 0  # 当前计算位置
    tuichu_time = 0  # 一次调频功能退出时间
    last_disturbance_time = 0
    while Initial_Position < len(pinlv):
        main_process(pinlv, toutui, fuhe)
    # print("本次计算大扰动偏差合格次数:" + str(D_Disturbance_mon_qualified_sum[t1.tm_mon]))
    # print("本次计算大扰动偏差不合格次数:" + str(D_Disturbance_mon_unqualified_sum[t1.tm_mon]))
    # print("本次计算小扰动偏差合格次数:" + str(S_Disturbance_mon_qualified_sum[t1.tm_mon]))
    # print("本次计算小扰动偏差不合格次数:" + str(S_Disturbance_mon_unqualified_sum[t1.tm_mon]))
    # print("一次调频退出时间" + str(tuichu_time))
    smallFreqCount = S_Disturbance_mon_qualified_sum[t1.tm_mon] + S_Disturbance_mon_unqualified_sum[
        t1.tm_mon]  # 日小频差动作次数
    largeFreqCount = D_Disturbance_mon_qualified_sum[t1.tm_mon] + D_Disturbance_mon_unqualified_sum[
        t1.tm_mon]  # 日大频差动作次数
    unqualifiedCount = D_Disturbance_mon_unqualified_sum[t1.tm_mon] + S_Disturbance_mon_unqualified_sum[
        t1.tm_mon]  # 日不合格次数
    regulationCount = smallFreqCount + largeFreqCount  # 本次一次调频动作次数
    exitTime = tuichu_time / 3600
    smallUnqCount = S_Disturbance_mon_unqualified_sum[t1.tm_mon]  # 小频差扰动不合格次数
    largeUnqCount = D_Disturbance_mon_unqualified_sum[t1.tm_mon]  # 大频差扰动不合格次数
    # ***************************退出考核电量计算***************************
    tuichu_F = (tuichu_time / 3600) * 0.02 * P_n
    # print("一次调频贡献率为：" + str(contribution_K))
    if len(contribution_K) == 0:
        contribution_K_average = 0
    else:
        contribution_K_average = round(np.mean(contribution_K) * 100, 2)
    # print("一次调频贡献率均值为：" + str(contribution_K_average))

    # **********************************数据回写***********************************888
    return_dict = {
        "regulationCount": regulationCount,
        "smallFreqCount": smallFreqCount,
        "largeFreqCount": largeFreqCount,
        "unqualifiedCount": unqualifiedCount,
        "exitTime": exitTime,
        "contribution": contribution_K_average,
        "smallUnqCount":smallUnqCount,
        "largeUnqCount":largeUnqCount

    }
    print(return_dict)
    response = requests.post(pyDataUrl, json=return_dict)
    print(response.text)
