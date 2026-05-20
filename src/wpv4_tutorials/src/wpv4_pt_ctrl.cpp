/*********************************************************************
* Software License Agreement (BSD License)
* 
*  Copyright (c) 2017-2020, Waterplus http://www.6-robot.com
*  All rights reserved.
* 
*  Redistribution and use in source and binary forms, with or without
*  modification, are permitted provided that the following conditions
*  are met:
* 
*   * Redistributions of source code must retain the above copyright
*     notice, this list of conditions and the following disclaimer.
*   * Redistributions in binary form must reproduce the above
*     copyright notice, this list of conditions and the following
*     disclaimer in the documentation and/or other materials provided
*     with the distribution.
*   * Neither the name of the WaterPlus nor the names of its
*     contributors may be used to endorse or promote products derived
*     from this software without specific prior written permission.
* 
*  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
*  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
*  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
*  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
*  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
*  FOOTPRINTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
*  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
*  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
*  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
*  LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
*  ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
*  POSSIBILITY OF SUCH DAMAGE.
*********************************************************************/
/* @author Zhang Wanjie                                             */

#include <ros/ros.h>
#include <std_msgs/String.h>
#include <sensor_msgs/JointState.h>
#include "dynamic_reconfigure/server.h"
#include "wpv4_tutorials/ptConfig.h"
#include <math.h>

static ros::Publisher pt_ctrl_pub;
static sensor_msgs::JointState pt_ctrl_msg;

void cbPT(wpv4_tutorials::ptConfig &config, uint32_t level) 
{
    ROS_WARN("旋转 tilt= %d", config.tilt);
    ROS_WARN("俯仰 pitch= %d ", config.pitch);
    pt_ctrl_msg.position[0] = config.tilt;
    pt_ctrl_msg.position[1] = config.pitch;
    pt_ctrl_pub.publish(pt_ctrl_msg);
}

int main(int argc, char** argv)
{
    setlocale(LC_ALL,"");
    ros::init(argc, argv, "wpv4_pt_ctrl");

    //云台控制消息包
    pt_ctrl_msg.name.resize(2);
    pt_ctrl_msg.position.resize(2);
    pt_ctrl_msg.velocity.resize(2);
    //云台角度
    pt_ctrl_msg.position[0] = 0;
    pt_ctrl_msg.position[1] = 0;
    //云台运动速度
    pt_ctrl_msg.velocity[0] = 1000;
    pt_ctrl_msg.velocity[1] = 1000;

    ros::NodeHandle nh;
    pt_ctrl_pub = nh.advertise<sensor_msgs::JointState>("/wpv4_pt/joint_ctrl_degree", 10);

    dynamic_reconfigure::Server<wpv4_tutorials::ptConfig> server;
    dynamic_reconfigure::Server<wpv4_tutorials::ptConfig>::CallbackType f;

    f = boost::bind(&cbPT, _1, _2);
    server.setCallback(f);

    ros::Time time = ros::Time(0);
    ros::Rate r(10);
    while(nh.ok())
    {
        ros::spinOnce();
        r.sleep();
    }
    return 0;
}
