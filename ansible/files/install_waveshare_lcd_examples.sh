wget https://www.waveshare.com/w/upload/b/bd/1.3inch_LCD_HAT_code.7z -O /tmp/1.3inch_LCD_HAT_code.7z
7z x /tmp/1.3inch_LCD_HAT_code.7z -o/tmp/1.3inch_LCD_HAT_code_7z
mv /tmp/1.3inch_LCD_HAT_code_7z/1.3inch_LCD_HAT_code ~/installers/waveshare_1.3inch_lcd_hat_code
rm ~/installers/waveshare_1.3inch_lcd_hat_code/fbtft/letitgo.mp4
find ~/installers/waveshare_1.3inch_lcd_hat_code -type d -exec chmod 755 '{}' \;
find ~/installers/waveshare_1.3inch_lcd_hat_code -type f -exec chmod 644 '{}' \;
