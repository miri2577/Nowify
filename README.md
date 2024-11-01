# Nowify-Vinyl

A fork of [Nowify](https://github.com/jonashcroft/Nowify) that focuses on the artwork, similar to displaying a vinyl record.

## Disclaimer! 
Before we start, i have absolutely no idea what i'm doing.
I've never developed or made anything besides basic Python scripts before, and i have never used GitHub either.
A combination of basic knowledge, ChatGPT, and 6 months of web dev education a decade ago i pretend to remember, we ended up here.
The code is most likely a mess, but hey it works for what i needed it to, so i'm sharing it here if anyone else can use it.

## About

The project is supposed to be responsive to most standard sizes and aspect ratios. Referring to the paragraph above, i'm sure it will act weird at some resolutions and aspect ratios.
Originally i wanted a 1:1 monitor to display like a vinyl, only to realize that didn't really exist.
Then my plan was a 4:3, only to find out there are not many decent modern quality 4:3 monitors.
So, i ended up upcycling a 16:9 laptop display instead. Insert image of when i'm finally finished with the display :)

Besides changing the styling and size of the elements, i also made the background a bit more fun to look at, by using the album art in a blurred version as the background.

The project is tested with the following resolutions:

3840x2160 - 4K  

3440x1440 - 1440p Ultrawide

1920x1080 - FHD

1080x1080 - FHD 1:1

480x320 - Raspberry Pi 4 Display

### 1080x1080 Preview
![1080x1080 Preview](assets/1080x1080.png?raw=true "Nowify-Vinyl preview image")
### 1920x1080 Preview
![1920x1080 Preview](assets/1920x1080.png?raw=true "Nowify-Vinyl preview image")
### 3440x1440 Preview
![3440x1440 Preview](assets/3440x1440.png?raw=true "Nowify-Vinyl preview image")
### 480x320 Preview
![480x320 Preview](assets/480x320.png?raw=true "Nowify-Vinyl preview image")

## To-do
- Is there a way to upscale the 640px album art dynamically for better quality/perceived resolution
- Settings panel for column/row displaying, upscaled art, background colors etc.


## Technical Limitations
From what i could find, the Spotify API's maximum artwork size is only 640x640. So if you have large and/or high resolution screens, unfortunately you will be stuck with 640x640.


For information on how to set up, visit the original [Nowify Repo](https://github.com/jonashcroft/Nowify) 
