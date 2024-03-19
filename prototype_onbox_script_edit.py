#/usr/bin/python3
from jnpr.junos import Device
from jnpr.junos.utils.start_shell import StartShell
from jnpr.junos.exception import SwRollbackError, RpcTimeoutError, RpcError
from junos import Junos_Trigger_Event
import jcs
import time, json
import re
from lxml import etree

def main():
    try:
        dev = Device()
        dev.open()
        
        rtr_op = dev.rpc.get_routing_task_replication_state()
        if rtr_op.findtext('.//task-re-mode', default='').lower() == 'backup':
            jcs.syslog("notice", "Found log CMLC on backup re please contact juniper")
            return
        message = str(Junos_Trigger_Event.xpath('//trigger-event/message')[0].text)
        print (f"Here is output : {message}")
        s_message  = message.split(" ")
        jcs.syslog("notice", "Event-script running !", s_message[1])
        # jcs.syslog("notice", "Event-script running !", s_message[1] + str(dev.facts.keys()))
        fpc_veri(s_message[1],dev)

        dev.close()
    except ImportError as e:
        return e

def fpc_veri(fpc_input,dev):
    with open("/var/db/scripts/event/cache.json", "r") as f:
        cache = json.load(f)
        
    # fpc_input = input("Enter : ")
    if cache["first"]:
        cache["lastet"]["name"] = fpc_input
        cache["lastet"]["time"] = int(time.time())
        cache["first"] = False
        with open("/var/db/scripts/event/cache.json", "w") as f:
            json.dump(cache, f)

    else:
        if cache["lastet"]["name"] == fpc_input:
            # print(f"({fpc_input}) detect same fpc event")
            jcs.syslog("notice", "Detect same fpc event => ", str(fpc_input))
            cache["lastet"]["time"] = int(time.time())
            with open("/var/db/scripts/event/cache.json", "w") as f:
                json.dump(cache, f)

        else:
            cur_time = int(time.time())
            lastet_time = cache["lastet"]["time"]
            old_fpc = cache["lastet"]["name"]
            cache["lastet"]["name"] = fpc_input
            cache["lastet"]["time"] = cur_time
            with open("/var/db/scripts/event/cache.json", "w") as f:
                json.dump(cache, f)

            if (cur_time - lastet_time) < 7200: # 7200 -> 2 x 60 x 60 = 2 hours
                # print(f"({fpc_input}) >>> SWITCHOVER RE <<< must switch over detect 2 events below 2 hours")
                jcs.syslog("notice", "Detect : ", str(old_fpc), " & ", str(fpc_input), " below 2 hours")
                swover_state = sw_validation_copy(dev)
                jcs.syslog("notice", "Switchover info : ", str(swover_state))
                if swover_state == True:
                    try:
                        jcs.syslog("notice", "Chassis Switchover Processing !")
                        req_res = dev.rpc.request_chassis_routing_engine_switch()
                        jcs.syslog("notice", "Chassis Switchover was completed")   #need to show where is the mater rightnow

                        cache["first"] = True
                        cache["lastet"]["name"] = ""
                        cache["lastet"]["time"] = 0
                        with open("/var/db/scripts/event/cache.json", "w") as f:
                            json.dump(cache, f)

                    except Exception as e:
                        jcs.syslog("notice", "Switch over failed ", str(e))
                    
                else:
                    jcs.syslog("notice", "Not successful")

            else:
                # print(f"({fpc_input}) detect 2 events more than 2 hours")
                jcs.syslog("notice", "Detect : ", str(old_fpc), " & ", str(fpc_input), " more than 2 hours")


def sw_validation_copy(dev):
    output = ''
    try:
        op = dev.rpc.request_shell_execute(
            routing_engine='backup',
            command="cli show system switchover")

        jcs.syslog("notice","Dataop : ",str(op))
        output = op.findtext('.//output', default='')
        jcs.syslog("notice","Dataop : ",str(output))
        gres_status = re.search(r'Switchover Status: Ready', output, re.I)
        if gres_status:
            return True
        else :
            jcs.syslog("notice",'Requirement FAILED: Graceful switchover status is not ready')
            return False

    except RpcError:
        # request-shell-execute rpc is not available for <14.1
        with StartShell(dev) as ss:
            ss.run('cli', '> ', timeout=5)
            if ss.run('request routing-engine '
                        'login other-routing-engine')[0]:
                # depending on user permission, prompt will go to either
                # cli or shell, below line of code prompt will finally end
                # up in cli mode
                ss.run('cli', '> ', timeout=5)
                data = ss.run('show system switchover', '> ', timeout=5)
                # for x in data:
                #     dataop.append(x)
                output = data[1]
                jcs.syslog("notice","Dataop : ",str(output))
                gres_status = re.search(r'Switchover Status: Ready', output, re.I)
                ss.run('exit')
                if gres_status:
                    return True
                else :
                    jcs.syslog("notice",'Requirement FAILED: Graceful switchover status is not ready')
                    return False
            else:
                return False


if __name__ == "__main__":
    main()
