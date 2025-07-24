# FileMaker Backend System - User Guide

*A simple explanation of what's running behind the scenes for your FileMaker database*

---

## What is this system?

This is an **automation system** that works with your FileMaker database to process photos and videos automatically. Think of it like having a smart assistant that can:

- Analyze your images and videos
- Generate descriptions using AI
- Extract technical information
- Keep everything organized in your FileMaker database

## What is an API?

An **API** (Application Programming Interface) is like a digital messenger. It's the way this automation system "talks" to your FileMaker database. 

**Here's how it works:**
- The system connects securely to your FileMaker database
- It can read information from your records
- It can update records with new information
- It processes items automatically when they're ready

Think of it like having a very efficient digital assistant that never sleeps and can process hundreds of items perfectly every time.

---

## 🚀 Main Features

### **AutoLog - The Smart Workflow**

The main feature is called **"AutoLog"** - it automatically finds items that need processing and handles everything for you.

**For Photos (Stills):**
- Finds photos marked as "Pending File Info"
- Extracts technical details (file size, dimensions, etc.)
- Copies files to the server
- Reads embedded photo information (EXIF data)
- Scrapes additional information from websites
- Generates AI descriptions
- Creates searchable tags
- Makes everything searchable

**For Videos (Footage):**
- Processes video files automatically
- Creates thumbnail images
- Generates frame-by-frame analysis
- Adds AI-generated descriptions
- Transcribes audio content
- Makes videos fully searchable

---

## 🔧 Available Tools

### **Photo Processing (Stills)**

#### **Complete Workflow**
- **`stills_autolog_00_run_all`** - Finds all pending photos and processes them completely
  - Runs automatically without any input needed
  - Processes multiple photos at the same time
  - Handles everything from start to finish

#### **Individual Steps** (for when you need more control)
- **`stills_autolog_01_get_file_info`** - Gets basic file information
- **`stills_autolog_02_copy_to_server`** - Copies files and creates thumbnails  
- **`stills_autolog_03_parse_metadata`** - Reads embedded photo data
- **`stills_autolog_04_scrape_url`** - Gets extra info from websites
- **`stills_autolog_05_generate_description`** - Creates AI descriptions (then auto-completes the rest)

#### **Photo Enhancement Tools**
- **`stills_upscale_image`** - Makes photos larger and higher quality using AI
- **`stills_rotate_thumbnail`** - Rotates thumbnail images 90 degrees
- **`stills_refresh_thumbnail`** - Recreates thumbnail from the original image

### **Video Processing (Footage)**

#### **Complete Workflow** 
- **`footage_autolog_00_run_all`** - Finds all pending videos and processes them
  - Creates thumbnails automatically
  - Analyzes video content frame by frame
  - Generates descriptions and searchable content

#### **Individual Steps**
- **`footage_autolog_01_get_file_info`** - Gets video file details
- **`footage_autolog_02_generate_thumbnails`** - Creates video thumbnail images
- **`footage_autolog_03_create_frames`** - Sets up frame-by-frame analysis
- **`footage_autolog_04_scrape_url`** - Gets additional information from websites
- **`footage_autolog_05_process_frames`** - Analyzes individual video frames
- **`footage_autolog_06_generate_description`** - Creates AI-powered video descriptions

### **Frame Analysis Tools**
- **`frames_generate_thumbnails`** - Creates thumbnail images from video frames
- **`frames_generate_captions`** - Describes what's happening in each frame
- **`frames_transcribe_audio`** - Converts speech to text from video audio

### **Import Tools**
- **`footage_import_ale`** - Imports video information from ALE files (Avid Log Exchange)
- **`metadata-bridge`** - Transfers information between different systems

---

## 🎯 How to Use This

### **For Most Users - Use the AutoLog**

The easiest way to use this system is through the **complete workflows**:

1. **For Photos**: Use `stills_autolog_00_run_all`
   - Just mark your photos as "Pending File Info" in FileMaker
   - The system automatically finds and processes them
   - Check back later - everything will be done

2. **For Videos**: Use `footage_autolog_00_run_all`  
   - Mark your videos as "Pending File Info" in FileMaker
   - The system handles all the complex video analysis
   - Creates searchable descriptions and transcriptions

### **For Advanced Users - Individual Tools**

If you need more control, you can run individual steps:
- Process specific items one at a time
- Re-run just one step if something needs fixing
- Enhance existing photos with upscaling or rotation tools

### **System Monitoring**

The system keeps track of everything it's doing:
- Shows how many jobs are running
- Tracks completed vs. in-progress items
- Provides detailed logs of what happened
- Can detect and fix stuck processes

---

## 💡 Key Benefits

**Time Saving**
- Processes hundreds of items automatically
- Works 24/7 without breaks
- Handles repetitive tasks perfectly every time

**AI-Powered Intelligence**  
- Generates detailed, accurate descriptions
- Creates searchable tags automatically
- Understands both visual and audio content

**Reliability**
- Automatically retries if something goes wrong
- Keeps detailed logs of all activity
- Can handle multiple items simultaneously

**Flexibility**
- Can process individual items or large batches
- Supports various input formats
- Integrates seamlessly with your existing FileMaker workflow

---

*This system runs in the background, constantly ready to help organize and enhance your digital archive. Just mark items as "Pending" in FileMaker, and let the automation take care of the rest!* 