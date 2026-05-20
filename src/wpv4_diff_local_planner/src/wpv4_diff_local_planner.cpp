#include <waterplus_local_planner/wpv4_diff_local_planner.h>
#include <waterplus_local_planner/wl_helper.h>
#include <tf_conversions/tf_eigen.h>
#include <pluginlib/class_list_macros.h>
#include <ros/ros.h>
#include <std_msgs/String.h>
#include <sensor_msgs/LaserScan.h>

// register this planner as a BaseLocalPlanner plugin
PLUGINLIB_EXPORT_CLASS( waterplus_local_planner::WPV4DiffLocalPlanner, nav_core::BaseLocalPlanner)

static float target_vel_x = 0;
static float target_vel_z = 0;
static float ac_vel_x = 0;
static float ac_vel_z = 0;
static float ranges[360];

namespace waterplus_local_planner
{
    static double fScaleD2R = 3.14159*0.5 / 180;
    //激光雷达回调(避障)
    void WPV4DiffLocalPlanner::lidarCallback(const sensor_msgs::LaserScan::ConstPtr& scan)
    {
        int nRanges = scan->ranges.size();
        // ROS_WARN("[WLP]range=%d ang= %.2f ",nRanges,scan->angle_increment); 
        for(int i=0;i<360;i++)
        {
            ranges[i] = scan->ranges[i];
        }
        SetRanges(ranges);
    }

    //构造函数
    WPV4DiffLocalPlanner::WPV4DiffLocalPlanner()
    {
        setlocale(LC_CTYPE, "");
        //ROS_WARN("[WLP]WPV4DiffLocalPlanner() ");  
        InitHelper();
        m_costmap_ros = NULL;
        m_tf_listener = NULL; 
        m_goal_reached = false;
        m_bInitialized = false;
        m_bAC = false;
        m_bFirstStep = true;
    }

    WPV4DiffLocalPlanner::~WPV4DiffLocalPlanner()
    {
    }

    void WPV4DiffLocalPlanner::initialize(std::string name, tf::TransformListener* tf, costmap_2d::Costmap2DROS* costmap_ros)
    {
        ROS_WARN("WPV4DiffLocalPlanner::initialize() - 1");
        if(!m_bInitialized)
        {	
            m_tf_listener = tf;
            m_costmap_ros = costmap_ros;
            m_costmap = m_costmap_ros->getCostmap();
            
            m_global_frame_id = m_costmap_ros->getGlobalFrameID();      //"odom"
            m_robot_base_frame_id = m_costmap_ros->getBaseFrameID();    //"base_footprint"
            
            m_footprint_spec = m_costmap_ros->getRobotFootprint();
            costmap_2d::calculateMinAndMaxDistances(m_footprint_spec, m_robot_inscribed_radius, m_robot_circumscribed_radius); 

            ros::NodeHandle nh_planner("~/" + name);
            nh_planner.param("max_vel_trans", m_max_vel_trans, 0.5);
            nh_planner.param("max_vel_rot", m_max_vel_rot, 0.5);
            nh_planner.param("max_acc_trans", m_max_acc_trans, 0.2);
            nh_planner.param("max_acc_rot", m_max_acc_rot, 0.2);
            nh_planner.param("acc_scale_trans", m_acc_scale_trans, 0.2);
            nh_planner.param("acc_scale_rot", m_acc_scale_rot, 0.3);
            nh_planner.param("path_dist_tolerance", m_path_dist_tolerance, 0.5);
            nh_planner.param("goal_dist_tolerance", m_goal_dist_tolerance, 0.2);
            nh_planner.param("goal_yaw_tolerance", m_goal_yaw_tolerance, 0.2);

            ROS_WARN("max_vel_trans = %.2f ",m_max_vel_trans);
            ROS_WARN("acc_scale_trans = %.2f ",m_acc_scale_trans);

            m_pub_target = nh_planner.advertise<geometry_msgs::PoseStamped>("local_planner_target", 10);
            m_scan_sub = nh_planner.subscribe<sensor_msgs::LaserScan>("/scan",1,&WPV4DiffLocalPlanner::lidarCallback,this);
            
            m_bInitialized = true;

            ROS_DEBUG("wpv4_diff_local_planner plugin initialized.");
        }
        else
        {
            ROS_WARN("wpv4_diff_local_planner has already been initialized, doing nothing.");
        }
    }

    void WPV4DiffLocalPlanner::initialize(std::string name,tf2_ros::Buffer* tf, costmap_2d::Costmap2DROS* costmap_ros)
    {
        ROS_WARN("WPV4DiffLocalPlanner::initialize() - 2");
        if(!m_bInitialized)
        {	
            m_tf_listener = new tf::TransformListener;
            m_costmap_ros = costmap_ros;
            m_costmap = m_costmap_ros->getCostmap();
            
            m_global_frame_id = m_costmap_ros->getGlobalFrameID();      //"odom"
            m_robot_base_frame_id = m_costmap_ros->getBaseFrameID();    //"base_footprint"
            
            m_footprint_spec = m_costmap_ros->getRobotFootprint();
            costmap_2d::calculateMinAndMaxDistances(m_footprint_spec, m_robot_inscribed_radius, m_robot_circumscribed_radius); 

            ros::NodeHandle nh_planner("~/" + name);
            nh_planner.param("max_vel_trans", m_max_vel_trans, 1.0);
            nh_planner.param("max_vel_rot", m_max_vel_rot, 1.0);
            nh_planner.param("max_acc_trans", m_max_acc_trans, 0.5);
            nh_planner.param("max_acc_rot", m_max_acc_rot, 0.5);
            nh_planner.param("acc_scale_trans", m_acc_scale_trans, 0.1);
            nh_planner.param("acc_scale_rot", m_acc_scale_rot, 0.3);
            nh_planner.param("path_dist_tolerance", m_path_dist_tolerance, 0.5);
            nh_planner.param("goal_dist_tolerance", m_goal_dist_tolerance, 0.2);
            nh_planner.param("goal_yaw_tolerance", m_goal_yaw_tolerance, 0.2);

            ROS_WARN("max_vel_trans = %.2f ",m_max_vel_trans);
            ROS_WARN("acc_scale_trans = %.2f ",m_acc_scale_trans);

            m_pub_target = nh_planner.advertise<geometry_msgs::PoseStamped>("local_planner_target", 10);
            m_scan_sub = nh_planner.subscribe<sensor_msgs::LaserScan>("/scan",1,&WPV4DiffLocalPlanner::lidarCallback,this);
            
            m_bInitialized = true;

            ROS_DEBUG("wpv4_diff_local_planner plugin initialized.");
        }
        else
        {
            ROS_WARN("wpv4_diff_local_planner has already been initialized, doing nothing.");
        }
    }

    bool WPV4DiffLocalPlanner::setPlan(const std::vector<geometry_msgs::PoseStamped>& plan)
    {
        // ROS_WARN("[WLP]setPlan() ");
        if(!m_bInitialized)
        {
            ROS_ERROR("wpv4_diff_local_planner has not been initialized, please call initialize() before using this planner");
            return false;
        }

        m_global_plan.clear();
        m_global_plan = plan;
        m_nPathIndex = 0;

        m_goal_reached = false;
        m_nStep = WLP_STEP_GOTO;
        
        return true;
    }

    static double CalDirectAngle(double inFromX, double inFromY, double inToX, double inToY)
    {
        double res = 0;
        double dx = inFromX - inToX;
        double dy = -(inFromY - inToY);
        if (dx == 0)
        {
            if (dy > 0)
            {
                res = 180 - 90;
            }
            else
            {
                res = 0 - 90;
            }

        }
        else
        {
            double fTan = dy / dx;
            res = atan(fTan) * 180 / 3.1415926;

            if (dx < 0)
            {
                res = res - 180;
            }

        }
        res = 180 - res;

        if (res < 0)
        {
            res += 360;
        }

        if (res > 360)
        {
            res -= 360;
        }

        res = res*3.1415926/180;

        return res;
    }

    static double AngleFix(double inAngle, double inMin, double inMax)
    {
        if (inMax - inMin > 6.28)
        {
            return inAngle;
        }
        
        double retAngle = inAngle;
        while (retAngle < inMin)
        {
            retAngle += 6.28;
        }
        while (retAngle > inMax)
        {
            retAngle -= 6.28;
        }
        return retAngle;
    }

    bool WPV4DiffLocalPlanner::computeVelocityCommands(geometry_msgs::Twist& cmd_vel)
    {
        // ROS_WARN("[WLP]computeVelocityCommands() ");
        if(!m_bInitialized)
        {
            ROS_ERROR("wpv4_diff_local_planner has not been initialized, please call initialize() before using this planner");
            return false;
        }

        int path_num = m_global_plan.size();
        if(path_num == 0)
        {
            return false;
        }

        cmd_vel.linear.x = 0;
        cmd_vel.linear.y = 0;
        cmd_vel.angular.z = 0;
        bool res = true;
        
        if(m_nStep == WLP_STEP_ARRIVED)
        {
            ROS_WARN("[WLP_ARRIVED](%.2f %.2f):%.2f",cmd_vel.linear.x,cmd_vel.linear.y,cmd_vel.angular.z);
            return true;
        }

         /////////////////////////////////////////////////////////////
        double goal_x,goal_y,goal_th;
        getTransformedPosition(m_global_plan.back(), m_robot_base_frame_id, goal_x, goal_y, goal_th);
        //ROS_WARN("goal(%.2f dy= %.2f) th= %.2f",goal_x, goal_y, goal_th);

        //  double face_goal = CalDirectAngle(0, 0, goal_x, goal_y);
        //  face_goal = AngleFix(face_goal,-2.1,2.1);
        //  ROS_WARN("face = %.2f goal(%.2f dy= %.2f) th= %.2f",face_goal, goal_x, goal_y, goal_th);
        
        if(m_nStep == WLP_STEP_GOTO)
        {
            // check if global goal is near
            double goal_dist = sqrt(goal_x*goal_x + goal_y*goal_y);
            if(goal_dist < m_goal_dist_tolerance)
            {
                // 足够靠近最终目标
                m_nStep = WLP_STEP_NEAR;
                ROS_WARN("[WLP-GOTO] -> [WLP_NEAR] (%.2f,%.2f) %.2f",goal_x, goal_y, goal_th);
            }
            else
            {
                // 未靠近最终目标，更新当前障碍物，准备避障
                ClearObst();
                SetRanges(ranges);
                //从后续的路径点中找距离自己最近的
                double minDist = 999;
                int nMinDistIndex = m_nPathIndex;
                double target_x, target_y, target_th;
                for(int i=m_nPathIndex;i<path_num;i++)
                {
                    getTransformedPosition(m_global_plan[i], m_robot_base_frame_id, target_x, target_y, target_th);
                    if( ChkTarget(target_y/0.05+50,target_x/0.05+50) == true)
                    {
                        double tmpDist = sqrt(target_x*target_x + target_y*target_y);
                        if(tmpDist < minDist && tmpDist >= m_goal_dist_tolerance)
                        {
                            nMinDistIndex = i;
                            minDist = tmpDist;
                        }
                    }
                }
                m_nPathIndex = nMinDistIndex;

                // 从距离自己最近的路径点往后遍历，在图中打点
                double gpath_x, gpath_y, gpath_th;
                ClearTarget();
                for(int i=m_nPathIndex;i<path_num;i++)
                {
                    getTransformedPosition(m_global_plan[i], m_robot_base_frame_id, gpath_x, gpath_y, gpath_th);
                    if(i == m_nPathIndex)
                    {
                        SetTarget(gpath_y/0.05+50,gpath_x/0.05+50,true);
                    }
                    else
                    {
                        SetTarget(gpath_y/0.05+50,gpath_x/0.05+50,false);
                    }
                }
                res = OutLine();
                // if(res == false)
                // {
                //     cmd_vel.linear.x = 0;
                //     cmd_vel.linear.y = 0;
                //     cmd_vel.angular.z = 0;
                //     return true;
                // }
                if(GetHelperNum() > 5 && (path_num - m_nPathIndex) > 1)
                {
                    target_x = GetFixX();
                    target_y = GetFixY();
                    gpath_x = GetFaceX();
                    gpath_y = GetFaceY();
                    //ROS_WARN("临时路径点大于5  target( %.2f , %.2f )  face (%.2f , %.2f )",target_x,target_y,gpath_x,gpath_y);
                }
                else
                {
                    getTransformedPosition(m_global_plan[m_nPathIndex], m_robot_base_frame_id, target_x, target_y, target_th);
                    int nFaceIndex = m_nPathIndex;
                    double face_x,face_y,face_th;
                    face_x = target_x;
                    face_y = target_y;
                    while(nFaceIndex < path_num)
                    {
                        getTransformedPosition(m_global_plan[nFaceIndex], m_robot_base_frame_id, face_x,face_y,face_th);
                        double tmpDist = sqrt(face_x*face_x + face_y*face_y);
                        if(tmpDist > 0.2)
                        {
                            break;
                        }
                        nFaceIndex ++;
                    }
                    gpath_x = face_x;
                    gpath_y = face_y;
                    gpath_th = face_th;

                    //getTransformedPosition(m_global_plan[m_nPathIndex], m_robot_base_frame_id, gpath_x, gpath_y, gpath_th);
                }
 
                // 计算速度
                //double face_target = CalDirectAngle(0, 0, gpath_x, gpath_y);
                double face_target = 0;
                // if((target_x !=gpath_x) || (target_y !=gpath_y) )
                // {
                //     face_target =CalDirectAngle(target_x, target_y, gpath_x, gpath_y);
                // }
                // else
                // {
                //     face_target = CalDirectAngle(0, 0, gpath_x, gpath_y);
                // }
                face_target = CalDirectAngle(0, 0, target_x, target_y);
                face_target = AngleFix(face_target,-2.1,2.1);
                if(fabs(face_target)> 0.8)
                {
                    //ROS_WARN("转弯角度大，原地打转");
                    target_vel_x = 0;
                    target_vel_z = face_target * m_acc_scale_rot;
                }
                else
                {
                    // start to move
                    target_vel_x = target_x * m_acc_scale_trans;
                    target_vel_z = face_target * m_acc_scale_rot;
                    //ROS_WARN("正常移动，速度 vx= %.2f   vz = %.2f",target_vel_x,target_vel_z);
                }
                m_pub_target.publish(m_global_plan[m_nPathIndex]);
            }
        }

        if(m_nStep == WLP_STEP_NEAR)
        {
            //到达目标点附近,调整朝向即可
            target_vel_x = 0;
            target_vel_z = goal_th;

            if(fabs(goal_th) < m_goal_yaw_tolerance)
            {
                m_goal_reached = true;
                m_nStep = WLP_STEP_ARRIVED;
                target_vel_z = 0;
                ROS_WARN("[WLP-ARRIVED] goal (%.2f,%.2f) %.2f",goal_x, goal_y, goal_th);

            }

            m_pub_target.publish(m_global_plan.back());
        }

        cmd_vel = m_last_cmd;
        
        //前后移动加速度控制
        if( fabs(target_vel_x - cmd_vel.linear.x) >  m_max_acc_trans)
        {
            //超过加速度极限,减小幅度
            if(target_vel_x > cmd_vel.linear.x)
            {
                cmd_vel.linear.x += m_max_acc_trans;
            }
            else
            {
                cmd_vel.linear.x -= m_max_acc_trans;
            }
        }
        else
        {
            cmd_vel.linear.x = target_vel_x;
        }

        //旋转加速度控制
        if( fabs(target_vel_z - cmd_vel.angular.z) >  m_max_acc_rot)
        {
            //超过加速度极限,减小幅度
            if(target_vel_z > cmd_vel.angular.z)
            {
                cmd_vel.angular.z += m_max_acc_rot;
            }
            else
            {
                cmd_vel.angular.z -= m_max_acc_rot;
            }
        }
        else
        {
            cmd_vel.angular.z = target_vel_z;
        }

        //速度极限控制
        if(cmd_vel.linear.x > m_max_vel_trans) cmd_vel.linear.x = m_max_vel_trans;
        if(cmd_vel.linear.x < -m_max_vel_trans) cmd_vel.linear.x = -m_max_vel_trans;
        if(cmd_vel.linear.y > m_max_vel_trans) cmd_vel.linear.y = m_max_vel_trans;
        if(cmd_vel.linear.y < -m_max_vel_trans) cmd_vel.linear.y = -m_max_vel_trans;
        if(cmd_vel.angular.z > m_max_vel_rot) cmd_vel.angular.z = m_max_vel_rot;
        if(cmd_vel.angular.z < -m_max_vel_rot) cmd_vel.angular.z = -m_max_vel_rot;

        m_last_cmd = cmd_vel;

        ROS_WARN("[WLP] target_x= %.2f,  vel=( %.2f , %.2f) ",target_vel_x, cmd_vel.linear.x,cmd_vel.angular.z);
        
        return true;
    }


    bool WPV4DiffLocalPlanner::isGoalReached()
    {
        //ROS_WARN("[WLP]isGoalReached() ");
        if (m_goal_reached)
        {
            ROS_INFO("GOAL Reached!");
            return true;
        }
        return false;
    }

    void WPV4DiffLocalPlanner::getTransformedPosition(geometry_msgs::PoseStamped& pose, std::string& frame_id, double& x, double& y, double& theta)
    {
        geometry_msgs::PoseStamped tf_pose;
        pose.header.stamp = ros::Time(0);
        m_tf_listener->transformPose(frame_id, pose, tf_pose);
        x = tf_pose.pose.position.x;
        y = tf_pose.pose.position.y,
        theta = tf::getYaw(tf_pose.pose.orientation);
    }

}