import shopify
import requests
import os
import time
import json
from PIL import Image
from io import BytesIO
from report_generator import generate_html_report, get_file_size_display
from concurrent.futures import ThreadPoolExecutor, as_completed

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

print(f"{Colors.BOLD}Please enter Shopify Access Tokens:{Colors.ENDC}")
jwl_access_token = input(f"{Colors.CYAN}Enter JWL Access Token: {Colors.ENDC}").strip()
jf_access_token = input(f"{Colors.CYAN}Enter JF Access Token: {Colors.ENDC}").strip()

# Store configurations
STORES = {
    "jwl": {
        "name": "Japan World Link",
        "shop_url": "japan-world-link.myshopify.com",
        "token": jwl_access_token
    },
    "jf": {
        "name": "Japan Toy and Figure",
        "shop_url": "japan-toy-and-figure.myshopify.com",
        "token": jf_access_token
    }
}

def select_store(auto_choice=None):
    """
    Select store and return shop URL and token.
    Args:
        auto_choice: Optional. Can be 1, 2, 'jwl', or 'jf' to auto-select without prompting.
    Returns:
        tuple: (shop_url, token)
    """
    if auto_choice is not None:
        choice = str(auto_choice).lower()
        if choice in ['1', 'jwl']:
            selected_store = STORES['jwl']
            print(f"{Colors.GREEN}✓ Auto-selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        elif choice in ['2', 'jf']:
            selected_store = STORES['jf']
            print(f"{Colors.GREEN}✓ Auto-selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        else:
            print(f"{Colors.RED}Invalid auto_choice: {auto_choice}. Falling back to manual selection.{Colors.ENDC}\n")
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
    print(f"{Colors.BOLD}Select Store:{Colors.ENDC}")
    print(f"  1. {Colors.GREEN}JWL{Colors.ENDC} - {STORES['jwl']['name']}")
    print(f"  2. {Colors.GREEN}JF{Colors.ENDC}  - {STORES['jf']['name']}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
    
    while True:
        choice = input(f"{Colors.BOLD}Enter your choice (1/2 or jwl/jf): {Colors.ENDC}").strip().lower()
        
        if choice in ['1', 'jwl']:
            selected_store = STORES['jwl']
            print(f"{Colors.GREEN}✓ Selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        elif choice in ['2', 'jf']:
            selected_store = STORES['jf']
            print(f"{Colors.GREEN}✓ Selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        else:
            print(f"{Colors.RED}Invalid choice. Please enter 1, 2, jwl, or jf.{Colors.ENDC}")

def fetch_products_generator(shop_url, token, batches_per_yield=100):
    """
    Generator that fetches products and yields them in chunks.
    Args:
        shop_url: Shopify store URL
        token: Access token
        batches_per_yield: Number of API batches (250 items each) to accumulate before yielding.
                           Default 100 batches = ~25,000 products.
    Yields:
        list: A chunk of product objects
    """
    api_version = "2024-01"
    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    products_chunk = []
    
    try:
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.CYAN}📦 Starting Rolling Fetch ({batches_per_yield} batches/chunk)...{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.ENDC}\n")
        
        page_size = 250
        since_id = None
        batch_count = 0
        total_fetched_so_far = 0
        
        while True:
            # Re-activate session before each API call (important after yield)
            shopify.ShopifyResource.activate_session(session)
            
            try:
                # Only pass since_id if we have a valid value
                if since_id:
                    print(f"  {Colors.CYAN}→ Fetching batch #{batch_count + 1} (since_id={since_id})...{Colors.ENDC}")
                    batch = shopify.Product.find(limit=page_size, since_id=since_id)
                else:
                    print(f"  {Colors.CYAN}→ Fetching first batch (no since_id)...{Colors.ENDC}")
                    batch = shopify.Product.find(limit=page_size)
                    
                print(f"  {Colors.GREEN}✓ Got batch, type: {type(batch)}, len: {len(batch) if hasattr(batch, '__len__') else 'N/A'}{Colors.ENDC}")
            except Exception as e:
                import traceback
                print(f"{Colors.RED}Error calling Shopify API: {e}{Colors.ENDC}")
                print(f"{Colors.YELLOW}Debug: since_id={since_id}, batch_count={batch_count}{Colors.ENDC}")
                print(f"{Colors.RED}Traceback:{Colors.ENDC}")
                traceback.print_exc()
                break
            
            # Check if batch is valid
            if batch is None or (isinstance(batch, list) and len(batch) == 0):
                break
            
            # Ensure batch is a list
            if not isinstance(batch, list):
                batch = [batch]
            
            batch_count += 1
            products_chunk.extend(batch)
            
            # Safely get the last product's ID
            try:
                since_id = batch[-1].id
            except (AttributeError, IndexError, TypeError) as e:
                print(f"{Colors.RED}Error getting product ID: {e}{Colors.ENDC}")
                break
                
            total_fetched_so_far += len(batch)
            
            if batch_count % 100 == 0:
                print(f"  {Colors.CYAN}→ Batch {batch_count}: Fetched {len(batch)} products (Total: {total_fetched_so_far}){Colors.ENDC}")
            
            # If we reached the limit for this chunk, yield it
            if batch_count % batches_per_yield == 0:
                print(f"\n{Colors.GREEN}✓ Accessing Chunk #{batch_count // batches_per_yield} ({len(products_chunk)} products)...{Colors.ENDC}")
                yield products_chunk
                products_chunk = [] # Reset for next chunk
                
            # time.sleep(0.1)  # Avoid rate limit
            
            if len(batch) < page_size:
                break
        
        # Yield remaining products if any
        if products_chunk:
            print(f"\n{Colors.GREEN}✓ Accessing Final Chunk ({len(products_chunk)} products)...{Colors.ENDC}")
            yield products_chunk
            
        print(f"\n{Colors.GREEN}✓ All products fetched! Total: {total_fetched_so_far}{Colors.ENDC}")
        
    except Exception as e:
        print(f"{Colors.RED}Error fetching products: {e}{Colors.ENDC}")
    finally:
        shopify.ShopifyResource.clear_session()

def get_image_size_head(url):
    """Fast fetch file size using HEAD request"""
    try:
        response = requests.head(url, timeout=5)
        if 'Content-Length' in response.headers:
            return int(response.headers['Content-Length'])
    except:
        pass
    return 0

def analyze_all_images(products):
    """
    Get sizes of all images from all products using concurrent HEAD requests.
    Returns list of tuples: (image_url, size, product_id, image_id, product_title)
    Sorted by size (largest first)
    """
    print(f"\n{Colors.BOLD}{Colors.YELLOW}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.YELLOW}⚡ Analyzing image sizes for current chunk...{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.YELLOW}{'='*60}{Colors.ENDC}\n")
    
    # Collect all image info
    image_info = []
    for product in products:
        for img in product.images:
            image_info.append({
                'url': img.src,
                'product_id': product.id,
                'image_id': img.id,
                'product_title': product.title
            })
    
    print(f"  {Colors.CYAN}Total images in chunk: {len(image_info)}{Colors.ENDC}")
    print(f"  {Colors.CYAN}Sending {len(image_info)} HEAD requests (5 concurrent workers)...{Colors.ENDC}\n")
    
    # Concurrent fetch sizes
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_info = {
            executor.submit(get_image_size_head, info['url']): info 
            for info in image_info
        }
        
        print(f"  {Colors.YELLOW}⏳ Started fetching sizes... (this may take a while){Colors.ENDC}")
        completed = 0
        for future in as_completed(future_to_info):
            info = future_to_info[future]
            try:
                size = future.result()
                results.append((info['url'], size, info['product_id'], info['image_id'], info['product_title']))
                completed += 1
                if completed % 500 == 0 or completed == len(image_info):
                    print(f"  {Colors.CYAN}Progress: {completed}/{len(image_info)} ({int(completed/len(image_info)*100)}%){Colors.ENDC}")
            except Exception as e:
                results.append((info['url'], 0, info['product_id'], info['image_id'], info['product_title']))
    
    # Partition: Images > 150KB first, <= 150KB last
    THRESHOLD = 150 * 1024  # 150KB
    large_images = [r for r in results if r[1] > THRESHOLD]
    small_images = [r for r in results if r[1] <= THRESHOLD]
    
    # Sort large images by size (largest first) for better impact
    large_images.sort(key=lambda x: x[1], reverse=True)
    
    # Combine: large first, then small
    results = large_images + small_images
    
    print(f"\n{Colors.GREEN}✓ Analysis complete!{Colors.ENDC}")
    print(f"  {Colors.CYAN}Images > 150KB: {len(large_images)} (will be processed){Colors.ENDC}")
    print(f"  {Colors.YELLOW}Images ≤ 150KB: {len(small_images)} (will be skipped){Colors.ENDC}")
    
    if large_images:
        print(f"  {Colors.GREEN}📊 Largest image: {get_file_size_display(large_images[0][1])}{Colors.ENDC}")
        print(f"  {Colors.GREEN}   Product: {large_images[0][4]} (ID: {large_images[0][2]}){Colors.ENDC}\n")
    else:
        print(f"  {Colors.YELLOW}⚠ No images > 150KB in this chunk!{Colors.ENDC}\n")
    
    return results

def get_bit_depth(mode):
    mode_mapping = {
        "1": 1, "L": 8, "P": 8, "RGB": 8, "RGBA": 8, 
        "CMYK": 8, "YCbCr": 8, "LAB": 8, "HSV": 8, 
        "I": 32, "F": 32
    }
    return mode_mapping.get(mode, "Unknown")

def analyze_image(image_url):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        file_size_bytes = len(image_data)
        
        img = Image.open(BytesIO(image_data))
        
        width, height = img.size
        mode = img.mode
        bands = img.getbands()
        channels = len(bands)
        bit_depth = get_bit_depth(mode)
        
        print(f"  > Start Analysis: {Colors.CYAN}{image_url}{Colors.ENDC}")
        
        return {
            "url": image_url,
            "size": file_size_bytes,
            "width": width,
            "height": height,
            "format": img.format,
            "mode": mode,
            "channels": f"{channels} ({', '.join(bands)})",
            "bit_depth": f"{bit_depth}-bit"
        }
        
    except Exception as e:
        print(f"    - {Colors.RED}Error analyzing image: {e}{Colors.ENDC}")
        return None

def resize_and_save_image(image_url, image_id):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        original_size = len(response.content)
        
        img = Image.open(BytesIO(response.content))
        
        # Check if image is already small (< 150KB)
        SMALL_IMAGE_THRESHOLD = 150 * 1024  # 150KB
        
        if original_size < SMALL_IMAGE_THRESHOLD:
            # Image is small - skip
            print(f"    {Colors.YELLOW}ℹ Original size {get_file_size_display(original_size)} < 150KB - Skipping{Colors.ENDC}")
            return None
        else:
            # Image is large - resize - compress
            MAX_SIZE = (1200, 1200)
            img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
            
            if img.mode == "P":
                img = img.convert("RGBA")
                
            output_path = f"resized_images/{image_id}.webp"

            MAX_FILE_SIZE = 100 * 1024 
            MIN_QUALITY = 20
            
            if original_size < MAX_FILE_SIZE:
                quality = 85
                print(f"    {Colors.CYAN}ℹ Original size {get_file_size_display(original_size)} < 100KB, using quality={quality}{Colors.ENDC}")
                img.save(output_path, "WEBP", quality=quality)
                new_size = os.path.getsize(output_path)
            else:
                quality = 50
                img.save(output_path, "WEBP", quality=quality)
                new_size = os.path.getsize(output_path)
                
                while new_size > MAX_FILE_SIZE and quality > MIN_QUALITY:
                    quality -= 2
                    print(f"    {Colors.YELLOW}⟳ File size {get_file_size_display(new_size)} > 100KB, re-compressing with quality={quality}...{Colors.ENDC}")
                    img.save(output_path, "WEBP", quality=quality)
                    new_size = os.path.getsize(output_path)
            
            if new_size > MAX_FILE_SIZE:
                print(f"    > Resized: {Colors.YELLOW}{output_path} ({get_file_size_display(new_size)}) - Warning: Still > 100KB at minimum quality{Colors.ENDC}")
            else:
                print(f"    > Resized: {Colors.GREEN}{output_path} ({get_file_size_display(new_size)}) - Quality: {quality}{Colors.ENDC}")
        
        mode = img.mode
        bands = img.getbands()
        channels = len(bands)
        bit_depth = get_bit_depth(mode)
        
        return {
            "path": output_path,
            "size": new_size,
            "width": img.width,
            "height": img.height,
            "format": "WEBP",
            "channels": f"{channels} ({', '.join(bands)})",
            "bit_depth": f"{bit_depth}-bit"
        }
        
    except Exception as e:
        print(f"    - {Colors.RED}Error resizing image: {e}{Colors.ENDC}")
        return None

def sync_images_to_shopify(product_id, report_data, shop_url, token):
    """Upload optimized images to Shopify and replace existing product images"""
    api_version = "2024-01"

    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    try:
        product = shopify.Product.find(product_id)
        print(f"\n{Colors.BOLD}{Colors.HEADER}Starting sync for: {product.title}{Colors.ENDC}")
        
        success_count = 0
        error_count = 0
        
        for data in report_data:
            image_id = data["id"]
            optimized_path = data["new"]["path"]
            
            try:
                print(f"\n{Colors.CYAN}Processing Image ID: {image_id}{Colors.ENDC}")
                
                target_image = None
                for img in product.images:
                    if img.id == image_id:
                        target_image = img
                        break
                
                if not target_image:
                    print(f"  {Colors.RED}✗ Image not found in product{Colors.ENDC}")
                    error_count += 1
                    continue
                
                with open(optimized_path, 'rb') as f:
                    image_data = f.read()
                
                position = target_image.position
                alt_text = target_image.alt if hasattr(target_image, 'alt') else None
                
                print(f"  {Colors.YELLOW}⟳ Deleting old image...{Colors.ENDC}")
                target_image.destroy()
                
                print(f"  {Colors.YELLOW}⟳ Uploading optimized image...{Colors.ENDC}")
                new_image = shopify.Image()
                new_image.product_id = product_id
                new_image.position = position
                if alt_text:
                    new_image.alt = alt_text
                
                import base64
                new_image.attachment = base64.b64encode(image_data).decode('utf-8')
                
                if new_image.save():
                    print(f"  {Colors.GREEN}✓ Successfully synced (Position: {position}){Colors.ENDC}")
                    success_count += 1
                    time.sleep(0.1)  # Avoid rate limit
                else:
                    print(f"  {Colors.RED}✗ Failed to upload: {new_image.errors.full_messages()}{Colors.ENDC}")
                    error_count += 1
                    
            except Exception as e:
                print(f"  {Colors.RED}✗ Error syncing image {image_id}: {e}{Colors.ENDC}")
                error_count += 1
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
        print(f"{Colors.BOLD}Sync Summary:{Colors.ENDC}")
        print(f"  {Colors.GREEN}✓ Success: {success_count}{Colors.ENDC}")
        print(f"  {Colors.RED}✗ Failed: {error_count}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}\n")
        
    except Exception as e:
        print(f"{Colors.RED}Error syncing to Shopify: {e}{Colors.ENDC}")
    finally:
        shopify.ShopifyResource.clear_session()


def get_product_images(product_id, shop_url, token, auto_sync=None):
    """
    Process product images: fetch, optimize, and optionally sync to Shopify.
    Args:
        product_id: Shopify product ID
        shop_url: Shopify store URL
        token: Access token
        auto_sync: Optional. True = auto sync, False = skip sync, None = ask user
    Returns:
        True if all images were skipped (small size), False otherwise
    """
    api_version = "2024-01"

    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    report_data = []

    try:
        product = shopify.Product.find(product_id)
        if not product:
            return True # Should not happen, but safe to skip

        print(f"{Colors.BOLD}Product Title: {Colors.BLUE}{product.title}{Colors.ENDC}")
        print(f"{Colors.BOLD}Processing Images...{Colors.ENDC}")
        for image in product.images:
            print(f"- Processing ID: {Colors.YELLOW}{image.id}{Colors.ENDC}")
            
            orig_stat = analyze_image(image.src)
            new_stat = resize_and_save_image(image.src, image.id)
            
            if orig_stat and new_stat:
                report_data.append({
                    "id": image.id,
                    "orig": orig_stat,
                    "new": new_stat
                })
            
            print("-" * 20)
            
    except Exception as e:
        print(f"{Colors.RED}Error fetching product: {e}{Colors.ENDC}")
        return False
    finally:
        shopify.ShopifyResource.clear_session()

    if report_data:
        filename = f"report-{product_id}.html"
        generate_html_report(report_data, filename=filename, product_id=product_id, shop_url=shop_url)
        
        should_sync = False
        
        if auto_sync is True:
            print(f"\n{Colors.GREEN}✓ Auto-sync enabled{Colors.ENDC}")
            should_sync = True
        elif auto_sync is False:
            print(f"\n{Colors.YELLOW}⊘ Auto-sync disabled - Skipping sync{Colors.ENDC}")
            should_sync = False
        else:
            print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
            print(f"{Colors.BOLD}Do you want to sync optimized images to Shopify? (yes/no): {Colors.ENDC}", end='')
            user_input = input().strip().lower()
            should_sync = user_input in ['yes', 'y']
        
        if should_sync:
            print(f"{Colors.BOLD}{Colors.GREEN}Starting sync process...{Colors.ENDC}")
            sync_images_to_shopify(product_id, report_data, shop_url, token)
            return False
        elif auto_sync is None:
            print(f"{Colors.YELLOW}Sync cancelled by user.{Colors.ENDC}")
            return False
            
    # If no report data, it means all images were skipped (small size)
    # Return True to signal that this product can be cached as skipped
    return True


if __name__ == "__main__":
    from report_generator import generate_index_html
    generate_index_html()    

    # Select store first
    shop_url, token = select_store(2)
    
    # Auto sync setting
    auto_sync = True
    
    # Load caches
    SKIPPED_CACHE_FILE = "skipped_products.json"
    PROCESSED_CACHE_FILE = "processed_products.json"
    
    skipped_products = set()
    if os.path.exists(SKIPPED_CACHE_FILE):
        try:
            with open(SKIPPED_CACHE_FILE, 'r') as f:
                skipped_products = set(json.load(f))
            print(f"{Colors.GREEN}✓ Loaded {len(skipped_products)} skipped products from cache{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}Error loading skipped cache: {e}{Colors.ENDC}")
    
    processed_products = set()
    if os.path.exists(PROCESSED_CACHE_FILE):
        try:
            with open(PROCESSED_CACHE_FILE, 'r') as f:
                processed_products = set(json.load(f))
            print(f"{Colors.GREEN}✓ Loaded {len(processed_products)} processed products from cache{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}Error loading processed cache: {e}{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}🎯 ROLLING BATCH MODE{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}Strategy: Fetch 100 Batches → Analyze → Process → Repeat{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
    
    # Rolling Batch Processing
    total_processed = 0
    all_processed_product_ids = set()
    
    # Use generator to fetch chunks of products (100 batches at a time)
    product_generator = fetch_products_generator(shop_url, token, batches_per_yield=1)
    
    for chunk_index, products_chunk in enumerate(product_generator):
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}� PROCESSING CHUNK #{chunk_index + 1}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}Products in this chunk: {len(products_chunk)}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
        
        if not products_chunk:
            continue
        
        # Check if all products in this chunk are already processed/skipped
        chunk_product_ids = {str(p.id) for p in products_chunk}
        already_handled = chunk_product_ids.issubset(processed_products | skipped_products)
        
        if already_handled:
            print(f"{Colors.GREEN}✓ All {len(products_chunk)} products in this chunk already processed/skipped - Skipping chunk!{Colors.ENDC}")
            continue
        
        unprocessed_count = len(chunk_product_ids - (processed_products | skipped_products))
        print(f"{Colors.CYAN}ℹ Found {unprocessed_count} unprocessed products in this chunk{Colors.ENDC}\n")
            
        # Step 1: Analyze images for this chunk and get priority list
        image_priority_list = analyze_all_images(products_chunk)
        
        if not image_priority_list:
            print(f"{Colors.YELLOW}No images found in this chunk - Continuing to next chunk...{Colors.ENDC}")
            continue
            
        # Step 2: Process images
        chunk_processed_count = 0
        chunk_processed_ids = set()
        consecutive_skips = 0  # Track consecutive skipped products
        
        total_images_in_chunk = len(image_priority_list)
        
        for idx, (url, size, product_id, image_id, product_title) in enumerate(image_priority_list, 1):
            product_id_str = str(product_id)
            
            # Skip if already processed in this chunk (product was handled when a larger image from it was processed)
            if product_id_str in chunk_processed_ids:
                continue
            
            # Skip if product already in global cache
            if product_id_str in processed_products:
                chunk_processed_ids.add(product_id_str)
                continue
            
            # Skip if product is in skip cache
            if product_id_str in skipped_products:
                chunk_processed_ids.add(product_id_str)
                continue
            
            # Check if report exists
            report_file = f"report-{product_id}.html"
            if os.path.exists(report_file):
                print(f"{Colors.YELLOW}» Product {product_id} already has report - Skipping{Colors.ENDC}")
                processed_products.add(product_id_str)
                chunk_processed_ids.add(product_id_str)
                continue
            
            # Process this product
            print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}{Colors.HEADER}[Chunk #{chunk_index + 1}] [Product #{total_processed + 1}] Priority #{idx}/{total_images_in_chunk}{Colors.ENDC}")
            print(f"{Colors.BOLD}Largest Unprocessed Image: {Colors.YELLOW}{get_file_size_display(size)}{Colors.ENDC}")
            print(f"{Colors.BOLD}Product: {product_title} (ID: {product_id}){Colors.ENDC}")
            print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}\n")
            
            is_fully_skipped = get_product_images(product_id, shop_url, token, auto_sync=auto_sync)
            
            # Update caches immediately
            if is_fully_skipped:
                skipped_products.add(product_id_str)
                consecutive_skips += 1  # Increment consecutive skip counter
                
                try:
                    with open(SKIPPED_CACHE_FILE, 'w') as f:
                        json.dump(list(skipped_products), f)
                except Exception as e:
                    print(f"{Colors.RED}Error saving skip cache: {e}{Colors.ENDC}")
                
                # If first product (largest image) is fully skipped, skip entire chunk
                if chunk_processed_count == 0:  # This is the first product we actually processed
                    print(f"\n{Colors.YELLOW}⚠ First product in chunk has all images < 150KB (skipped){Colors.ENDC}")
                    print(f"{Colors.YELLOW}  → All remaining products in this chunk will also be skipped{Colors.ENDC}")
                    print(f"{Colors.YELLOW}  → Skipping entire chunk!{Colors.ENDC}\n")
                    break
                
                # If 3 consecutive products are skipped, skip entire chunk
                if consecutive_skips >= 3:
                    print(f"\n{Colors.YELLOW}⚠ {consecutive_skips} consecutive products skipped (all images < 150KB){Colors.ENDC}")
                    print(f"{Colors.YELLOW}  → Remaining products will likely be skipped too{Colors.ENDC}")
                    print(f"{Colors.YELLOW}  → Skipping rest of chunk!{Colors.ENDC}\n")
                    break
                    
            else:
                processed_products.add(product_id_str)
                consecutive_skips = 0  # Reset counter on successful processing
                
                try:
                    with open(PROCESSED_CACHE_FILE, 'w') as f:
                        json.dump(list(processed_products), f)
                except Exception as e:
                    print(f"{Colors.RED}Error saving processed cache: {e}{Colors.ENDC}")
            
            chunk_processed_count += 1
            chunk_processed_ids.add(product_id_str)
            total_processed += 1
            all_processed_product_ids.add(product_id_str)
            
            # Generate index after each product
            generate_index_html()
            
            print(f"\n{Colors.CYAN}Total processed: {total_processed} | Chunk progress: {chunk_processed_count} products{Colors.ENDC}")

        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Finished processing Chunk #{chunk_index + 1}{Colors.ENDC}\n")

    # Final summary
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}✓ ALL PROCESSING COMPLETED!{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.GREEN}Total products processed: {total_processed}{Colors.ENDC}")
    print(f"{Colors.GREEN}Products skipped (small images): {len(skipped_products)}{Colors.ENDC}")
    print(f"{Colors.GREEN}Total unique products handled: {len(all_processed_product_ids)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}\n")
