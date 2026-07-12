# PCB-To-Path-Generator

This repository currently contains the Proof of Concept for the PCB To Path Generator Software (PPG) and its demonstrating automatic extraction of (X,Y) coordinates for the SCARA Robot from a .drl file providede by the user. 

The main purpose of the software is to automate or significantly reduce the time consumed by manual programming of soldering systems. 

// Working

PPG uses an PTH (Plated Through Hole) .drl file provided by the user. The PTH file contains decimal values for the location of the holes in the PCB, PTH files are mainly developed for PCB Drilling Machines as they use these locations to drill holes.

An PTH(Plated Through Hole) File contains 3 main information for an CNC Machine:

1) Drilling Tool Size
2) X,Y Coordinates of the centre of the holes
3) Diameter of the hole

Out of these 3 information we only use 2 for our SCARA Robot, namely X,Y Coordinates and Diameter.

// From X,Y To Robot X,Y

After getting the .csv file with the X,Y Coordinates and Diameter of the holes, now we convert these coordinates into SCARA Robots Coordinate System. 

