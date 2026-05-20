#include "SerialCom.h"
#pragma once

class CMPU_driver : public CSerialCom
{
public:
    CMPU_driver();
    ~CMPU_driver();
    void Parse(unsigned char inData);

	unsigned char m_ParseBuf[128];
	int m_nRecvIndex;			//��������
	unsigned char m_lastRecv;	//��һ���ַ�
	bool m_bFrameStart;			//֡������ʼ
	int m_nFrameLength;			//֡����

	int m_nRecvFrameCnt;
	int m_nRecvByteCnt;

	double fQuatW;
	double fQuatX;
	double fQuatY;
	double fQuatZ;
	
	double fGyroX;
	double fGyroY;
	double fGyroZ;
	
	double fAccX;
	double fAccY;
	double fAccZ;

	float ypr[3];           // [yaw, pitch, roll]   yaw/pitch/roll container and gravity vector
    float m_fYaw;
	float m_fPitch;
	float m_fRoll;

protected:
	void m_ParseFrame(unsigned char *inBuf, int inLen);
	double m_CalQuaternionVal(unsigned char *inBuf);
};