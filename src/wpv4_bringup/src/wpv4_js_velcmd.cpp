#include <ros/ros.h>
#include <sensor_msgs/Joy.h>
#include <geometry_msgs/Twist.h>

static float vel_acc = 0.01;  //移动速度的加速度

using namespace std;

class TeleopJoy
{
public:
  TeleopJoy();
  bool bStart;
  float lx;
  float ry;
  float target_vel_x;
  ros::NodeHandle n;
  ros::Subscriber sub;
  ros::Time current_time;
  ros::Time last_time;
  ros::Publisher velcmd_pub;
  geometry_msgs::Twist vel_cmd;
  void SendVelcmd();
private:
  void callBack(const sensor_msgs::Joy::ConstPtr& joy);
};

TeleopJoy::TeleopJoy()
{
  lx = 0;
  ry = 0;
  target_vel_x = 0;
  bStart = false;
  velcmd_pub = n.advertise<geometry_msgs::Twist>("/cmd_vel",10);
  sub = n.subscribe<sensor_msgs::Joy>("joy",10,&TeleopJoy::callBack,this);
  current_time = ros::Time::now();
  last_time = ros::Time::now();
 
  ROS_INFO("TeleopJoy");
}

static float kx = 0.25;
static float ky = 0.25;
void TeleopJoy::callBack(const sensor_msgs::Joy::ConstPtr& joy)
{

  ROS_INFO("Joy: [%.2f , %.2f]", lx , ry);
  lx = joy->axes[1];
  ry = joy->axes[3];
  target_vel_x = (float)lx*kx;
  bStart = true;
}


void TeleopJoy::SendVelcmd()
{
  if(bStart == false)
    return;
  float diff_x = target_vel_x - vel_cmd.linear.x;
  if(fabs(diff_x) > vel_acc)
  {
    if(diff_x > 0)
      vel_cmd.linear.x += vel_acc;
    else   
      vel_cmd.linear.x -= vel_acc;
  }
  else
    vel_cmd.linear.x = target_vel_x;
  vel_cmd.linear.y = 0;
  vel_cmd.linear.z = 0;
  vel_cmd.angular.x = 0;
  vel_cmd.angular.y = 0;
  vel_cmd.angular.z = (float)ry*ky;
  velcmd_pub.publish(vel_cmd);
}


int main(int argc, char** argv)
{
  ros::init(argc, argv, "wpv4_js_velcmd");

  TeleopJoy cTeleopJoy;

  ros::Rate r(30);
  while(ros::ok())
  {
    cTeleopJoy.SendVelcmd();
    ros::spinOnce();
    r.sleep();
  }

  return 0;
}
